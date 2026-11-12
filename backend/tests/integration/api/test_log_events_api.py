"""日志事件查询 API。"""

LOG_TEXT = """[    0.000000] usb 1-1: new high-speed USB device number 2 using xhci_hcd
[    0.100000] usb 1-1: device descriptor read/64, error -71
[    0.200000] usb 1-1: device not accepting address 2, error -71
[    0.300000] system boot complete
"""


class TestLogEventsApi:
    def test_upload_parse_and_query_events(self, client):
        upload = client.post(
            "/api/v1/logs/upload",
            files={"file": ("kernel.log", LOG_TEXT.encode("utf-8"), "text/plain")},
        )
        assert upload.status_code == 200, upload.text
        log_id = upload.json()["id"]

        parsed = client.post(f"/api/v1/logs/{log_id}/parse")
        assert parsed.status_code == 200, parsed.text
        assert parsed.json()["event_count"] > 0

        data = client.get(f"/api/v1/logs/{log_id}/events/query").json()
        assert data["total"] > 0
        assert data["items"][0]["line_no"] >= 1

        errors = client.get(
            f"/api/v1/logs/{log_id}/events/query", params={"is_error": True},
        ).json()
        assert errors["total"] > 0
        assert all(item["is_error"] for item in errors["items"])

        paged = client.get(
            f"/api/v1/logs/{log_id}/events/query", params={"page": 1, "page_size": 2},
        ).json()
        assert len(paged["items"]) <= 2
