"""知识模板自定义 API。"""

from app.core.config import settings
from app.services.knowledge import template_store


class TestKnowledgeTemplatesApi:
    def test_update_and_reset_template(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            settings, "KNOWLEDGE_TEMPLATE_FILE", str(tmp_path / "templates.json"),
        )
        template_store._cache["mtime"] = None
        template_store._cache["data"] = {}

        updated = client.put("/api/v1/knowledge/templates/faq", json={
            "guide": "自定义说明：按问题/处理填写",
            "sections": [
                {"title": "问题", "key": "symptom", "level": "required"},
                {"title": "处理", "key": "solution", "level": "required"},
            ],
        })
        assert updated.status_code == 200, updated.text
        payload = updated.json()
        assert payload["guide"] == "自定义说明：按问题/处理填写"
        assert payload["is_customized"] is True

        listed = client.get("/api/v1/knowledge/templates").json()["templates"]
        faq = next(item for item in listed if item["doc_type"] == "faq")
        assert faq["guide"] == "自定义说明：按问题/处理填写"

        reset = client.delete("/api/v1/knowledge/templates/faq")
        assert reset.status_code == 200
        assert reset.json()["is_customized"] is False
        assert reset.json()["guide"] != "自定义说明：按问题/处理填写"
