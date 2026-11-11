"""知识库标准化 API：入库规范化、分节、剧本、质量分、预览与审核。"""

CASE_MD = """# 潜江 D3C 紧急报警上传异常

## 现象

潜江的 D3C 设备，同样版本，有的车紧急报警上传视频，有的不上传

## 原因

上报司机手动命令:1 后平台下发 9206 文件上传，录像未写盘导致 -5007

## 处理结果

平台处理
"""

CASE_MD_VALID = (
    CASE_MD
    + "\n\n## 日志特征\n\n### 关键词\n\n- 紧急报警\n- 9206\n\n### 正则\n\n- (?i)9206\n"
)


class TestKnowledgeStandardizationApi:
    def test_create_standardizes_and_persists(self, client):
        resp = client.post("/api/v1/knowledge", json={
            "title": "案例", "content": CASE_MD, "doc_type": "case",
        })
        assert resp.status_code == 201, resp.text
        doc = resp.json()
        assert doc["status"] == "active"
        assert doc.get("quality_score") is not None

        sections = client.get(f"/api/v1/knowledge/{doc['id']}/sections").json()["sections"]
        keys = [s["section_key"] for s in sections]
        assert "symptom" in keys
        assert "root_cause" in keys

        profile = client.get(f"/api/v1/knowledge/{doc['id']}/profile").json()
        assert profile["source"] == "template"
        assert "潜江" in (profile["symptom"] or "")

        items = client.get("/api/v1/knowledge").json()["items"]
        item = next(i for i in items if i["id"] == doc["id"])
        assert item["quality_score"] is not None

    def test_draft_on_missing_required(self, client):
        md = CASE_MD_VALID.replace("## 处理结果", "## 备注")
        resp = client.post("/api/v1/knowledge", json={
            "title": "缺项", "content": md, "doc_type": "case",
        })
        assert resp.status_code == 201, resp.text
        doc = resp.json()
        assert doc["status"] == "draft"
        assert any(i["code"] == "MISSING_REQUIRED_SECTION" for i in doc["issues"])

    def test_format_preview(self, client):
        resp = client.post("/api/v1/knowledge/format/preview", json={
            "content": CASE_MD, "doc_type": "case",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["normalized_content"]
        assert data["profile_draft"]["symptom"]
        assert "issues" in data

    def test_templates(self, client):
        resp = client.get("/api/v1/knowledge/templates")
        assert resp.status_code == 200
        assert len(resp.json()["templates"]) == 4
