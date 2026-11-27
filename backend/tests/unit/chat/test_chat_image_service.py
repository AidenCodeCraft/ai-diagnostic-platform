"""对话截图识别测试（假 Provider，不发真实请求）。"""

import pytest

from app.models import ChatImageUpload
from app.services.providers.vision import VisionProviderError
from app.services.vision.image_service import ChatImageError, ChatImageService, sniff_mime
from app.services.vision.routing import PATH_OCR, PATH_OCR_VISION, PATH_VISION, analyze_text, decide_path

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64

LOG_TEXT = "\n".join(
    [
        "[2026-08-02 14:21:59]  [NL668_4G_GetRegSta.. 0719] pri:  s8RegNetName:CHINA MOBILE",
        "[2026-08-02 14:22:01]  [RMSG_SYS_AV_VOLUME.. 0418] pri:  Volume:27",
        "[2026-08-02 14:22:09]  [NET] register failed ret=-1",
    ]
)


class FakeProvider:
    def __init__(self, ocr_text="", ocr_error=None, vision_text="弹窗提示：网络未注册", vision_error=None):
        self.ocr_text = ocr_text
        self.ocr_error = ocr_error
        self.vision_text = vision_text
        self.vision_error = vision_error
        self.ocr_calls = 0
        self.vision_calls = 0

    def ocr(self, data, filename):
        self.ocr_calls += 1
        if self.ocr_error:
            raise VisionProviderError(self.ocr_error)
        return {"text": self.ocr_text, "pages": 1, "usage": {"input_tokens": 100}}

    def describe(self, data, mime, prompt):
        self.vision_calls += 1
        if self.vision_error:
            raise VisionProviderError(self.vision_error)
        return {"text": self.vision_text, "usage": {"total_tokens": 500}}


class FakeStorage:
    def __init__(self):
        self.saved = []

    def save(self, local_path, filename, project_id=None):
        self.saved.append((str(local_path), filename, project_id))
        return f"minio://diag-logs/chat/{filename}"


def build_service(db_session, provider=None, storage=None):
    return ChatImageService(db_session, provider=provider or FakeProvider(), storage=storage or FakeStorage())


def test_sniff_mime_detects_real_types():
    assert sniff_mime(PNG) == "image/png"
    assert sniff_mime(JPG) == "image/jpeg"
    assert sniff_mime(b"%PDF-1.7") is None


def test_routing_log_screenshot_uses_ocr():
    assert decide_path(LOG_TEXT) == PATH_OCR


def test_routing_short_ui_text_uses_vision():
    assert decide_path("网络未注册") == PATH_VISION


def test_routing_ocr_failure_uses_vision():
    assert decide_path("", ocr_failed=True) == PATH_VISION


def test_analyze_text_counts_log_signals():
    stats = analyze_text(LOG_TEXT)
    assert stats.line_with_ts == 3
    assert stats.module_id_hits >= 2
    assert stats.looks_like_log is True


def test_upload_log_screenshot_indexes_by_ocr(db_session):
    provider = FakeProvider(ocr_text=LOG_TEXT)
    service = build_service(db_session, provider)

    record = service.upload(PNG, "log.png", session_id=None, user_id=1)

    assert record.status == "succeeded"
    assert record.recognize_path == PATH_OCR
    assert "register failed" in record.extracted_text
    assert provider.vision_calls == 0, "日志截图不应触发视觉调用（省钱且保真）"
    assert record.storage_ref.startswith("minio://")


def test_upload_ui_screenshot_falls_back_to_vision(db_session):
    provider = FakeProvider(ocr_text="确认", vision_text="弹窗：SIM 卡未插入")
    service = build_service(db_session, provider)

    record = service.upload(PNG, "ui.png")

    assert record.status == "succeeded"
    # OCR 也拿到了一点文字，因此记为 ocr+vision（两条结果都保留，便于人工核对）
    assert record.recognize_path == PATH_OCR_VISION
    assert "SIM 卡未插入" in record.extracted_text
    assert "确认" in record.extracted_text
    assert provider.vision_calls == 1


def test_ocr_failure_still_answers_via_vision(db_session):
    provider = FakeProvider(ocr_error="OCR 返回 413", vision_text="图表：信号强度在第 20 秒归零")
    service = build_service(db_session, provider)

    record = service.upload(PNG, "chart.png")

    assert record.status == "succeeded"
    assert record.recognize_path == PATH_VISION
    assert "第 20 秒归零" in record.extracted_text


def test_both_paths_fail_marks_failed_without_raising(db_session):
    provider = FakeProvider(ocr_error="超时", vision_error="模型不可用")
    service = build_service(db_session, provider)

    record = service.upload(PNG, "x.png")

    assert record.status == "failed"
    assert record.error_message
    assert record.extracted_text is None


def test_same_image_reuses_previous_text(db_session):
    provider = FakeProvider(ocr_text=LOG_TEXT)
    service = build_service(db_session, provider)

    first = service.upload(PNG, "a.png")
    second = service.upload(PNG, "a-copy.png")

    assert second.status == "succeeded"
    assert second.extracted_text == first.extracted_text
    assert second.usage.get("reused_from") == first.id
    assert provider.ocr_calls == 1, "同一张图不应重复调用 OCR（重复计费）"


def test_rejects_non_image_payload(db_session):
    service = build_service(db_session)
    with pytest.raises(ChatImageError):
        service.upload(b"%PDF-1.7 not an image", "a.pdf")


def test_rejects_oversized_image(db_session):
    service = build_service(db_session)
    with pytest.raises(ChatImageError):
        service.upload(PNG + b"0" * (33 * 1024 * 1024), "big.png")


def test_texts_for_session_returns_succeeded_only(db_session):
    service = build_service(db_session, FakeProvider(ocr_text=LOG_TEXT))
    ok = service.upload(PNG, "a.png", session_id=5)
    assert ok.status == "succeeded"

    failed_service = build_service(db_session, FakeProvider(ocr_error="x", vision_error="y"))
    failed_service.upload(JPG, "b.png", session_id=5)

    texts = ChatImageService(db_session).texts_for_session(5)

    assert len(texts) == 1
    assert texts[0]["image_id"] == ok.id
    assert "register failed" in texts[0]["text"]


def test_bind_to_session_links_images_for_send(db_session):
    service = build_service(db_session, FakeProvider(ocr_text=LOG_TEXT))
    first = service.upload(PNG, "a.png", user_id=1)
    second = service.upload(JPG, "b.png", user_id=1)

    bound = service.bind_to_session([first.id, second.id], 9, user_id=1)

    assert bound == 2
    assert db_session.query(ChatImageUpload).filter_by(session_id=9).count() == 2
    assert len(ChatImageService(db_session).texts_for_session(9)) == 2


def test_bind_ignores_other_users_images(db_session):
    service = build_service(db_session, FakeProvider(ocr_text=LOG_TEXT))
    record = service.upload(PNG, "a.png", user_id=1)

    bound = service.bind_to_session([record.id], 9, user_id=2)

    assert bound == 0
    assert db_session.query(ChatImageUpload).filter_by(session_id=9).count() == 0


# ------------------------------------------------------------------
# 与 DeepSeek 官方文档对齐的行为（vision / ocr 两篇 guide）
# ------------------------------------------------------------------


def test_sniff_mime_supports_gif_bmp_tiff_and_rejects_wav():
    from app.services.vision.image_service import sniff_mime

    assert sniff_mime(b"GIF89a-rest") == "image/gif"
    assert sniff_mime(b"BM1234") == "image/bmp"
    assert sniff_mime(bytes([0x49, 0x49, 0x2A, 0x00]) + b"rest") == "image/tiff"
    # RIFF 开头但不是 WebP：音频不能当图片处理
    assert sniff_mime(b"RIFF" + b"\x00" * 4 + b"WAVEfmt ") is None


def test_provider_normalizes_base_url_to_v1():
    """OCR 文档地址是 /v1/tools/ocr：配置只写域名时必须补 /v1。"""
    from app.services.providers.vision import DeepSeekVisionProvider

    p1 = DeepSeekVisionProvider(api_key="k", base_url="https://api.deepseek.com")
    p2 = DeepSeekVisionProvider(api_key="k", base_url="https://api.deepseek.com/v1/chat/completions")
    assert p1.api_root == "https://api.deepseek.com/v1"
    assert p2.api_root == "https://api.deepseek.com/v1"


def test_provider_raises_on_200_with_error_object(monkeypatch):
    """文档：识别开始后失败仍是 HTTP 200，响应体换成 error 对象。"""
    import httpx

    from app.services.providers.vision import DeepSeekVisionProvider, VisionProviderError

    provider = DeepSeekVisionProvider(api_key="k", base_url="https://api.deepseek.com/v1")

    class FakeResponse:
        status_code = 200
        text = '{"error": {"message": "OCR did not finish in time", "code": "gateway_timeout_error"}}'

        def json(self):
            return {"error": {"message": "OCR did not finish in time"}}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    with pytest.raises(VisionProviderError) as exc:
        provider.ocr(b"x", "a.png")
    assert "did not finish" in str(exc.value)


def test_provider_flags_truncated_pages(monkeypatch):
    """finish_reason=length 表示该页文本不完整，必须显式带出来。"""
    import httpx

    from app.services.providers.vision import DeepSeekVisionProvider

    provider = DeepSeekVisionProvider(api_key="k", base_url="https://api.deepseek.com/v1")

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "id": "ocr-1",
                "page_count": 2,
                "pages": [
                    {"index": 0, "text": "第一页", "finish_reason": "stop"},
                    {"index": 1, "text": "第二页…", "finish_reason": "length"},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = provider.ocr(b"x", "a.png")
    assert result["pages"] == 2
    assert result["truncated_pages"] == [1]
    assert "第一页" in result["text"]


def test_provider_maps_ocr_status_codes(monkeypatch):
    import httpx
    import pytest as _pytest

    from app.services.providers.vision import DeepSeekVisionProvider, VisionProviderError

    provider = DeepSeekVisionProvider(api_key="k", base_url="https://api.deepseek.com/v1")

    class FakeResponse:
        status_code = 413
        text = '{"error": {"message": "file is too large"}}'

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    with _pytest.raises(VisionProviderError) as exc:
        provider.ocr(b"x", "a.png")
    assert "413" in str(exc.value) and "文件过大" in str(exc.value)


# ----------------------------------------------------------------------
# 管理后台多模型配置的凭据解析
# ----------------------------------------------------------------------


def _admin_llm_config(monkeypatch, llm_cfg):
    """替换后台配置文件读取，让凭据解析测试不依赖 data/raw。"""
    from app.services.providers import deepseek_provider

    monkeypatch.setattr(deepseek_provider, "_load_admin_llm_config", lambda: llm_cfg)


def test_resolve_admin_llm_config_prefers_requested_model(monkeypatch):
    from app.services.providers.deepseek_provider import resolve_admin_llm_config

    _admin_llm_config(monkeypatch, {
        "models": [
            {"provider": "deepseek", "model": "deepseek-v4-pro", "api_key": "sk-pro", "base_url": "https://pro.example"},
            {"provider": "deepseek", "model": "deepseek-flash", "api_key": "sk-flash", "base_url": "https://flash.example"},
        ]
    })
    cfg = resolve_admin_llm_config("deepseek-flash")
    assert cfg == {
        "api_key": "sk-flash",
        "base_url": "https://flash.example",
        "model": "deepseek-flash",
    }


def test_resolve_admin_llm_config_falls_back_to_default_and_ignores_mask(monkeypatch):
    from app.services.providers.deepseek_provider import resolve_admin_llm_config

    _admin_llm_config(monkeypatch, {
        "models": [
            # 首选模型不存在 → 回退默认模型；掩码 key 不能当真实密钥
            {"provider": "deepseek", "model": "deepseek-v4-flash", "api_key": "****abcd", "base_url": "", "isDefault": True},
            {"provider": "deepseek", "model": "deepseek-v4-pro", "api_key": "sk-pro", "base_url": "https://api.deepseek.com"},
        ]
    })
    cfg = resolve_admin_llm_config("deepseek-flash")
    assert cfg["model"] == "deepseek-v4-flash"
    assert cfg["api_key"] == "sk-pro"
    assert cfg["base_url"] == "https://api.deepseek.com"


def test_resolve_admin_llm_config_supports_legacy_single_model(monkeypatch):
    from app.services.providers.deepseek_provider import resolve_admin_llm_config

    _admin_llm_config(monkeypatch, {
        "api_key": "sk-legacy",
        "base_url": "https://legacy.example/v1/chat/completions",
        "model": "deepseek-chat",
    })
    cfg = resolve_admin_llm_config("deepseek-flash")
    assert cfg["api_key"] == "sk-legacy"
    assert cfg["base_url"] == "https://legacy.example/v1/chat/completions"


def test_vision_provider_reads_key_from_admin_models(monkeypatch):
    """回归：后台按 models[] 保存 Key 后，截图识别必须能读到（原先只读顶层字段）。"""
    from app.core.config import settings
    from app.services.providers.vision import DeepSeekVisionProvider

    _admin_llm_config(monkeypatch, {
        "models": [
            {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "api_key": "sk-admin",
                "base_url": "https://api.deepseek.com",
                "isDefault": True,
            }
        ]
    })
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_VISION_MODEL", raising=False)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")

    provider = DeepSeekVisionProvider()
    assert provider.available is True
    assert provider.api_key == "sk-admin"
    assert provider.api_root == "https://api.deepseek.com/v1"
    assert provider.model == "deepseek-flash"


def test_vision_provider_missing_key_points_to_admin_config(monkeypatch):
    from app.core.config import settings
    from app.services.providers.vision import DeepSeekVisionProvider, VisionProviderError

    _admin_llm_config(monkeypatch, {})
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")

    provider = DeepSeekVisionProvider()
    with pytest.raises(VisionProviderError) as exc:
        provider.ocr(b"x", "a.png")
    assert "管理后台" in str(exc.value)
    assert "DEEPSEEK_API_KEY" in str(exc.value)
