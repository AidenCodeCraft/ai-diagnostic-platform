"""会话置顶：置顶排在最前，取消后恢复普通排序。"""


class TestChatPinned:
    def test_pin_and_unpin(self, client, admin_headers):
        first = client.post(
            "/api/v1/chat-sessions", json={"title": "older"}, headers=admin_headers,
        ).json()
        second = client.post(
            "/api/v1/chat-sessions", json={"title": "newer"}, headers=admin_headers,
        ).json()

        # 置顶较早的会话 → 列表首位
        resp = client.put(
            f"/api/v1/chat-sessions/{first['id']}",
            json={"is_pinned": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_pinned"] is True

        items = client.get("/api/v1/chat-sessions", headers=admin_headers).json()["items"]
        assert items[0]["id"] == first["id"]
        assert items[1]["id"] == second["id"]

        # 取消置顶 → 字段恢复 false
        resp = client.put(
            f"/api/v1/chat-sessions/{first['id']}",
            json={"is_pinned": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_pinned"] is False

    def test_rename_via_update_session(self, client, admin_headers):
        created = client.post(
            "/api/v1/chat-sessions", json={"title": "旧标题"}, headers=admin_headers,
        ).json()
        resp = client.put(
            f"/api/v1/chat-sessions/{created['id']}",
            json={"title": "新标题"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "新标题"
