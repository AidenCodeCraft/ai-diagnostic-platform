"""AI 润色 API（LLM 不可用时回退规则规范化）。"""

ROUGH = """设备是D3C，版本V2.1，潜江现场。紧急报警上传视频有时成功有时失败。
平台下发9206后返回-5007，怀疑录像没写盘。
处理：确认司机是否手动触发，检查写盘状态。
"""


class TestKnowledgePolishApi:
    def test_polish_falls_back_to_rules(self, client):
        resp = client.post("/api/v1/knowledge/polish", json={
            "content": ROUGH, "doc_type": "case", "title": "D3C 上传异常",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["source"] == "rule"
        assert data["polished_content"]
        assert data["notes"]
        assert not any(issue["level"] == "error" for issue in data["issues"])

    def test_templates_expose_skeleton_and_example(self, client):
        resp = client.get("/api/v1/knowledge/templates")
        assert resp.status_code == 200
        templates = resp.json()["templates"]
        for item in templates:
            assert item["skeleton"].strip()
            assert item["guide"].strip()
            assert item["example"].strip()

    def test_polish_requires_content(self, client):
        resp = client.post("/api/v1/knowledge/polish", json={"content": "", "doc_type": "case"})
        assert resp.status_code == 422
