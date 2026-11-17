"""系统参数（多对话并行 / 同时在线人数）与并发提问闸门测试。"""

import pytest

from app.services.system.concurrency import ConcurrencyGate
from app.services.system.system_config import get_system_config, normalize


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """把 system_config.json 指向临时文件，避免污染真实配置。"""
    cfg_file = tmp_path / "system_config.json"
    import app.api.admin as admin_module
    import app.services.system.system_config as sc

    monkeypatch.setattr(admin_module, "CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(sc, "CONFIG_FILE", str(cfg_file))
    return cfg_file


class TestSystemConfig:
    def test_defaults_when_file_missing(self, isolated_config):
        cfg = get_system_config()
        assert cfg["max_upload_mb"] == 100
        assert cfg["timeout_seconds"] == 300
        assert cfg["log_retention_days"] == 90
        assert cfg["parallel_chat_enabled"] is True
        assert cfg["max_parallel_chats"] == 3
        assert cfg["max_online_users"] == 200

    def test_normalize_accepts_camelcase_and_drops_junk(self):
        cfg = normalize({"maxUploadMb": 42, "maxOnlineUsers": 500, "junk": 1})
        assert cfg["max_upload_mb"] == 42
        assert cfg["max_online_users"] == 500
        assert "junk" not in cfg

    def test_normalize_rejects_bad_values(self):
        cfg = normalize({"max_online_users": "abc", "parallel_chat_enabled": ""})
        assert cfg["max_online_users"] == 200  # 非法值回退默认
        assert cfg["parallel_chat_enabled"] is False  # bool("") == False

    def test_round_trip_via_admin_api(self, client, isolated_config):
        body = {
            "max_upload_mb": 120,
            "timeout_seconds": 240,
            "log_retention_days": 30,
            "parallel_chat_enabled": False,
            "max_parallel_chats": 5,
            "max_online_users": 800,
        }
        resp = client.put("/api/v1/admin/config/system", json=body)
        assert resp.status_code == 200
        got = client.get("/api/v1/admin/config/system").json()
        for key, value in body.items():
            assert got[key] == value

    def test_save_tolerates_camelcase(self, client, isolated_config):
        resp = client.put("/api/v1/admin/config/system", json={"maxOnlineUsers": 300})
        assert resp.status_code == 200
        got = client.get("/api/v1/admin/config/system").json()
        assert got["max_online_users"] == 300
        assert got["max_upload_mb"] == 100  # 未提交字段保持默认


class TestConcurrencyGate:
    def test_acquire_release(self):
        gate = ConcurrencyGate()
        assert gate.acquire(2) is True
        assert gate.acquire(2) is True
        assert gate.acquire(2) is False
        gate.release()
        assert gate.acquire(2) is True
        assert gate.inflight == 2
        gate.release()
        gate.release()
        assert gate.inflight == 0

    def test_zero_limit_means_unlimited(self):
        gate = ConcurrencyGate()
        for _ in range(50):
            assert gate.acquire(0) is True
        assert gate.inflight == 50


class TestChatConcurrencyLimit:
    def test_stream_rejected_when_full(self, client, isolated_config):
        client.put("/api/v1/admin/config/system", json={"max_online_users": 1})
        from app.services.system.concurrency import chat_gate

        assert chat_gate.acquire(1) is True
        try:
            resp = client.post("/api/v1/chat-sessions/1/stream", json={"content": "hi"})
            assert resp.status_code == 200  # SSE 始终 200，错误以事件返回
            assert "当前同时在线人数已达上限" in resp.text
        finally:
            chat_gate.release()

    def test_chat_rejected_when_full(self, client, isolated_config):
        client.put("/api/v1/admin/config/system", json={"max_online_users": 1})
        from app.services.system.concurrency import chat_gate

        assert chat_gate.acquire(1) is True
        try:
            resp = client.post("/api/v1/chat-sessions/1/chat", json={"content": "hi"})
            assert resp.status_code == 429
            assert "当前同时在线人数已达上限" in resp.json()["detail"]
        finally:
            chat_gate.release()

    def test_gate_released_after_stream(self, client, isolated_config):
        from app.services.system.concurrency import chat_gate

        session = client.post(
            "/api/v1/chat-sessions", json={"title": "t", "model": "mock"}
        ).json()
        resp = client.post(
            f"/api/v1/chat-sessions/{session['id']}/stream", json={"content": "hi"}
        )
        assert resp.status_code == 200
        assert '"done"' in resp.text
        assert chat_gate.inflight == 0

    def test_stats_exposes_active_chat_streams(self, client, isolated_config):
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 200
        assert "active_chat_streams" in resp.json()
        assert resp.json()["active_chat_streams"] == 0

    def test_provider_stream_closed_on_client_disconnect(self, db_session, monkeypatch):
        """客户端停止/断开（gen.close()）必须显式关闭上游 LLM 流。"""
        closed = {"v": False}

        class FakeProvider:
            def chat_stream(self, messages):
                try:
                    yield "t1"
                    yield "t2"
                finally:
                    closed["v"] = True

        from app.services.chat.chat_service import ChatService

        monkeypatch.setattr(
            ChatService, "_get_provider", classmethod(lambda cls, name: FakeProvider())
        )
        svc = ChatService(db_session)
        session = svc.create_session(title="t", model="mock")
        gen = svc.send_message_stream(session_id=session.id, content="hi")  # type: ignore[arg-type]

        try:
            for _ in range(20):
                chunk = next(gen, None)
                if chunk is None or '"token"' in chunk:
                    break
        except StopIteration:
            pass
        gen.close()  # 模拟客户端断开
        assert closed["v"] is True
