"""Tests for chat message edit-version history and per-user theme preferences."""

import pytest


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _create_session(client):
    resp = client.post(
        "/api/v1/chat-sessions", json={"title": "t", "model": "mock"}
    )
    assert resp.status_code in (200, 201)
    return resp.json()


def _register(client, username="alice"):
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "Secret123!@#"},
    )
    assert resp.status_code == 200
    return resp.json()


# ------------------------------------------------------------------
# Message versions (编辑重发保留历史)
# ------------------------------------------------------------------

class TestMessageVersions:
    def test_add_message_with_versions(self, client):
        session = _create_session(client)
        resp = client.post(
            f"/api/v1/chat-sessions/{session['id']}/messages",
            json={
                "role": "user",
                "content": "修改后的提问",
                "versions": [
                    {"content": "原始提问"},
                    {"content": "修改后的提问"},
                ],
                "active_version": 1,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "修改后的提问"
        assert [v["content"] for v in data["versions"]] == ["原始提问", "修改后的提问"]
        assert data["active_version"] == 1

    def test_update_message_keeps_both_versions(self, client):
        session = _create_session(client)
        msg = client.post(
            f"/api/v1/chat-sessions/{session['id']}/messages",
            json={"role": "user", "content": "原始提问"},
        ).json()

        resp = client.put(
            f"/api/v1/chat-sessions/{session['id']}/messages/{msg['id']}",
            json={
                "content": "修改后的提问",
                "versions": [
                    {"content": "原始提问"},
                    {"content": "修改后的提问"},
                ],
                "active_version": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert [v["content"] for v in data["versions"]] == ["原始提问", "修改后的提问"]
        assert data["active_version"] == 1

        # 刷新历史：GET 消息返回两个版本
        msgs = client.get(f"/api/v1/chat-sessions/{session['id']}/messages").json()
        assert len(msgs) == 1
        assert msgs[0]["content"] == "修改后的提问"
        assert [v["content"] for v in msgs[0]["versions"]] == ["原始提问", "修改后的提问"]

    def test_update_message_switches_active_version(self, client):
        session = _create_session(client)
        msg = client.post(
            f"/api/v1/chat-sessions/{session['id']}/messages",
            json={
                "role": "user",
                "content": "v2",
                "versions": [{"content": "v1"}, {"content": "v2"}],
                "active_version": 1,
            },
        ).json()
        resp = client.put(
            f"/api/v1/chat-sessions/{session['id']}/messages/{msg['id']}",
            json={"content": "v1", "active_version": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "v1"
        assert resp.json()["active_version"] == 0

    def test_update_message_not_found(self, client):
        session = _create_session(client)
        resp = client.put(
            f"/api/v1/chat-sessions/{session['id']}/messages/99999",
            json={"content": "x"},
        )
        assert resp.status_code == 404

    def test_update_message_ignores_unknown_fields(self, client):
        session = _create_session(client)
        msg = client.post(
            f"/api/v1/chat-sessions/{session['id']}/messages",
            json={"role": "user", "content": "a"},
        ).json()
        resp = client.put(
            f"/api/v1/chat-sessions/{session['id']}/messages/{msg['id']}",
            json={"content": "b", "role": "assistant", "session_id": 999},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "user"
        assert resp.json()["session_id"] == session["id"]


# ------------------------------------------------------------------
# 用户主题偏好（每个用户独立配置）
# ------------------------------------------------------------------

class TestUserThemePreferences:
    def test_default_theme_is_null(self, client):
        token = _register(client)["access_token"]
        resp = client.get(
            "/api/v1/auth/preferences",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["theme"] is None

    def test_save_and_get_theme(self, client):
        token = _register(client)["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.put(
            "/api/v1/auth/preferences", json={"theme": "dark"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["theme"] == "dark"
        resp = client.get("/api/v1/auth/preferences", headers=headers)
        assert resp.json()["theme"] == "dark"

    def test_invalid_theme_rejected(self, client):
        token = _register(client)["access_token"]
        resp = client.put(
            "/api/v1/auth/preferences",
            json={"theme": "blue"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_theme_is_per_user(self, client):
        token_a = _register(client, "alice")["access_token"]
        token_b = _register(client, "bob")["access_token"]
        client.put(
            "/api/v1/auth/preferences",
            json={"theme": "dark"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        client.put(
            "/api/v1/auth/preferences",
            json={"theme": "light"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert (
            client.get(
                "/api/v1/auth/preferences",
                headers={"Authorization": f"Bearer {token_a}"},
            ).json()["theme"]
            == "dark"
        )
        assert (
            client.get(
                "/api/v1/auth/preferences",
                headers={"Authorization": f"Bearer {token_b}"},
            ).json()["theme"]
            == "light"
        )

    def test_requires_token(self, client):
        assert client.get("/api/v1/auth/preferences").status_code == 401
        assert (
            client.put(
                "/api/v1/auth/preferences", json={"theme": "dark"}
            ).status_code
            == 401
        )
