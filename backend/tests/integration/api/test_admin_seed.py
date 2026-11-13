"""管理后台种子数据接口。"""


class TestAdminSeed:
    def test_seed_endpoint_creates_and_skips(self, client):
        first = client.post("/api/v1/admin/knowledge/seed")
        assert first.status_code == 200, first.text
        assert first.json()["created"] == 4
        assert first.json()["skipped"] == 0

        second = client.post("/api/v1/admin/knowledge/seed")
        assert second.status_code == 200
        assert second.json()["created"] == 0
        assert second.json()["skipped"] == 4

    def test_seed_reset_rebuilds(self, client):
        client.post("/api/v1/admin/knowledge/seed")
        reset = client.post("/api/v1/admin/knowledge/seed", params={"reset": True})
        assert reset.status_code == 200
        assert reset.json()["deleted"] == 4
        assert reset.json()["created"] == 4
