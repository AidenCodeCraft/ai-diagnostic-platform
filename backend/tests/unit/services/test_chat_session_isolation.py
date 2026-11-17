"""会话按用户隔离：不同登录用户只能看到/访问自己的对话。

用户场景：developer 与 engineer 分别登录后，各自看到的对话列表与内容
必须不同——此前会话未绑定用户、列表不按用户过滤，所有登录用户看到
同一份全局对话。
"""

from __future__ import annotations

import uuid

PASSWORD = "Str0ng!Passw0rd"  # 满足 UserCreate 密码强度校验（≥12 位+大小写+数字+特殊字符）


def _register(client, username: str):
    # 避开种子用户与用例间重名：追加唯一后缀
    username = f"{username}_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": PASSWORD, "role": "user"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]["id"]


def _create_session(client, headers, title: str):
    resp = client.post("/api/v1/chat-sessions", json={"title": title}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestChatSessionIsolation:
    def test_list_sessions_only_returns_own(self, client):
        dev_headers, _ = _register(client, "developer")
        eng_headers, _ = _register(client, "engineer")

        _create_session(client, dev_headers, "开发者的对话一")
        _create_session(client, dev_headers, "开发者的对话二")
        _create_session(client, eng_headers, "工程师的对话")

        dev_list = client.get("/api/v1/chat-sessions", headers=dev_headers).json()
        eng_list = client.get("/api/v1/chat-sessions", headers=eng_headers).json()

        dev_titles = {s["title"] for s in dev_list["items"]}
        eng_titles = {s["title"] for s in eng_list["items"]}
        assert dev_titles == {"开发者的对话一", "开发者的对话二"}
        assert eng_titles == {"工程师的对话"}

    def test_cross_user_session_access_rejected(self, client):
        dev_headers, _ = _register(client, "developer")
        eng_headers, _ = _register(client, "engineer")
        dev_session = _create_session(client, dev_headers, "开发者的对话")

        sid = dev_session["id"]
        # engineer 访问 developer 的会话：一律 404（不泄露存在性）
        assert client.get(f"/api/v1/chat-sessions/{sid}", headers=eng_headers).status_code == 404
        assert client.get(f"/api/v1/chat-sessions/{sid}/messages", headers=eng_headers).status_code == 404
        assert client.post(
            f"/api/v1/chat-sessions/{sid}/messages",
            json={"role": "user", "content": "hi"}, headers=eng_headers,
        ).status_code == 404
        assert client.put(
            f"/api/v1/chat-sessions/{sid}", json={"title": "改标题"}, headers=eng_headers,
        ).status_code == 404
        assert client.delete(f"/api/v1/chat-sessions/{sid}", headers=eng_headers).status_code == 404
        # 本人访问正常
        assert client.get(f"/api/v1/chat-sessions/{sid}", headers=dev_headers).status_code == 200

    def test_stream_endpoint_requires_ownership(self, client):
        dev_headers, _ = _register(client, "developer")
        eng_headers, _ = _register(client, "engineer")
        dev_session = _create_session(client, dev_headers, "开发者的对话")

        resp = client.post(
            f"/api/v1/chat-sessions/{dev_session['id']}/stream",
            json={"content": "你好"}, headers=eng_headers,
        )
        assert resp.status_code == 404

    def test_create_session_ignores_body_user_id(self, client):
        """会话归属以 JWT 为准，请求体里的 user_id 不可信。"""
        dev_headers, dev_id = _register(client, "developer")
        _, eng_id = _register(client, "engineer")

        resp = client.post(
            "/api/v1/chat-sessions",
            json={"title": "冒名会话", "user_id": eng_id},
            headers=dev_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["user_id"] == dev_id

    def test_missing_or_invalid_token_rejected(self, client):
        _register(client, "developer")
        assert client.get("/api/v1/chat-sessions").status_code == 401
        assert client.get(
            "/api/v1/chat-sessions",
            headers={"Authorization": "Bearer not-a-jwt"},
        ).status_code == 401
        assert client.post(
            "/api/v1/chat-sessions", json={"title": "x"},
        ).status_code == 401

    def test_messages_isolated_between_users(self, client):
        dev_headers, _ = _register(client, "developer")
        eng_headers, _ = _register(client, "engineer")

        dev_session = _create_session(client, dev_headers, "开发者的对话")
        eng_session = _create_session(client, eng_headers, "工程师的对话")
        client.post(
            f"/api/v1/chat-sessions/{dev_session['id']}/messages",
            json={"role": "user", "content": "developer 的私有内容"}, headers=dev_headers,
        )

        dev_msgs = client.get(
            f"/api/v1/chat-sessions/{dev_session['id']}/messages", headers=dev_headers,
        ).json()
        eng_msgs = client.get(
            f"/api/v1/chat-sessions/{eng_session['id']}/messages", headers=eng_headers,
        ).json()
        assert [m["content"] for m in dev_msgs] == ["developer 的私有内容"]
        assert eng_msgs == []
