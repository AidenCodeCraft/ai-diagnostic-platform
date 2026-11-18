"""角色限制：知识库读接口、client-logs 仅 admin/developer 可用。"""

CLIENT_LOG_PAYLOAD = {
    "entries": [{
        "id": "test-log-1",
        "timestamp": "2026-11-18T00:00:00Z",
        "level": 4,
        "category": "api",
        "message": "role restriction test",
    }],
}


class TestKnowledgeReadRole:
    def test_engineer_forbidden(self, client, engineer_headers):
        assert client.get("/api/v1/knowledge", headers=engineer_headers).status_code == 403
        assert client.get("/api/v1/knowledge/tree", headers=engineer_headers).status_code == 403
        assert client.get("/api/v1/knowledge/search", params={"q": "x"}, headers=engineer_headers).status_code == 403

    def test_admin_allowed(self, client, admin_headers):
        assert client.get("/api/v1/knowledge", headers=admin_headers).status_code == 200
        assert client.get("/api/v1/knowledge/tree", headers=admin_headers).status_code == 200

    def test_anonymous_forbidden(self, anon_client):
        assert anon_client.get("/api/v1/knowledge").status_code == 401

    def test_image_endpoint_stays_public_for_img_tags(self, anon_client):
        # 图片由 <img src> 加载，无法携带 Authorization，必须保持开放
        assert anon_client.get("/api/v1/knowledge/images/999999").status_code != 401


class TestClientLogsRole:
    def test_requires_admin(self, anon_client, client, engineer_headers):
        assert anon_client.post("/api/v1/client-logs/batch", json=CLIENT_LOG_PAYLOAD).status_code == 401
        assert client.post(
            "/api/v1/client-logs/batch", json=CLIENT_LOG_PAYLOAD, headers=engineer_headers,
        ).status_code == 403

    def test_admin_can_ingest(self, client, admin_headers):
        assert client.post(
            "/api/v1/client-logs/batch", json=CLIENT_LOG_PAYLOAD, headers=admin_headers,
        ).status_code == 201


class TestChatSessionOrdering:
    def test_new_message_moves_session_to_top(self, client, admin_headers):
        first = client.post(
            "/api/v1/chat-sessions", json={"title": "older"}, headers=admin_headers,
        ).json()
        second = client.post(
            "/api/v1/chat-sessions", json={"title": "newer"}, headers=admin_headers,
        ).json()
        assert second["id"] != first["id"]

        # 给较早的会话发消息后，它应排到最前
        resp = client.post(
            f"/api/v1/chat-sessions/{first['id']}/messages",
            json={"role": "user", "content": "hi"},
            headers=admin_headers,
        )
        assert resp.status_code == 201

        items = client.get("/api/v1/chat-sessions", headers=admin_headers).json()["items"]
        assert items[0]["id"] == first["id"]
