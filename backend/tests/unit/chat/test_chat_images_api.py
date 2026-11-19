"""截图上传接口测试（Provider 打桩，不发真实请求）。"""

from app.services.providers.vision import DeepSeekVisionProvider

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
LOG_TEXT = "[2026-08-02 14:22:09]  [NET] register failed ret=-1\n" * 3


def stub_ocr(monkeypatch, text=LOG_TEXT):
    monkeypatch.setattr(
        DeepSeekVisionProvider,
        "ocr",
        lambda self, data, filename: {"text": text, "pages": 1, "usage": {"input_tokens": 10}},
    )


def test_upload_returns_recognized_text(client, admin_headers, monkeypatch):
    stub_ocr(monkeypatch)

    resp = client.post(
        "/api/v1/chat/images",
        files={"file": ("log.png", PNG, "image/png")},
        data={"session_id": "1"},
        headers=admin_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["recognize_path"] == "ocr"
    assert "register failed" in body["text"]
    assert body["id"] > 0


def test_upload_rejects_non_image(client, admin_headers, monkeypatch):
    stub_ocr(monkeypatch)

    resp = client.post(
        "/api/v1/chat/images",
        files={"file": ("a.pdf", b"%PDF-1.7 hello", "application/pdf")},
        headers=admin_headers,
    )

    assert resp.status_code == 400
    assert "PNG" in resp.json()["detail"]


def test_upload_requires_auth(anon_client, monkeypatch):
    stub_ocr(monkeypatch)

    resp = anon_client.post(
        "/api/v1/chat/images",
        files={"file": ("log.png", PNG, "image/png")},
    )

    assert resp.status_code in (401, 403)


def test_get_image_returns_record(client, admin_headers, monkeypatch):
    stub_ocr(monkeypatch)
    created = client.post(
        "/api/v1/chat/images",
        files={"file": ("log.png", PNG, "image/png")},
        headers=admin_headers,
    ).json()

    resp = client.get(f"/api/v1/chat/images/{created['id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
