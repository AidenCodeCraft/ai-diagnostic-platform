"""知识库读权限：普通登录用户（售后/测试）必须能查看原文与引用来源。

背景：对话里点开参考来源会请求 GET /knowledge/{id}，此前该接口挂的是
require_admin，user 角色拿到 403「需要管理员权限」，引用等于点不开。
规则：读接口对**所有登录用户**开放；写接口（上传/新建/编辑/删除/模板）仍限管理员。
"""

from __future__ import annotations


class TestKnowledgeReadPermissions:
    def _make_doc(self, client):
        resp = client.post(
            "/api/v1/knowledge",
            json={
                "title": "线路超速报警排查",
                "content": "## 超速报警\n\n检查 JT1078 报警参数与阈值配置。",
                "doc_type": "manual",
                "status": "active",
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_anon_requires_auth(self, anon_client):
        assert anon_client.get("/api/v1/knowledge").status_code == 401
        assert anon_client.get("/api/v1/knowledge/tree").status_code == 401

    def test_user_can_list_and_browse(self, client, engineer_headers):
        self._make_doc(client)

        assert client.get("/api/v1/knowledge", headers=engineer_headers).status_code == 200
        assert client.get("/api/v1/knowledge/tree", headers=engineer_headers).status_code == 200
        assert client.get("/api/v1/knowledge/categories", headers=engineer_headers).status_code == 200
        assert client.get(
            "/api/v1/knowledge/search", params={"q": "超速"}, headers=engineer_headers,
        ).status_code == 200

    def test_user_can_open_document_and_sections(self, client, engineer_headers):
        """这两条就是对话里「点开引用来源」走的接口。"""
        doc_id = self._make_doc(client)

        detail = client.get(f"/api/v1/knowledge/{doc_id}", headers=engineer_headers)
        assert detail.status_code == 200
        assert detail.json()["title"] == "线路超速报警排查"

        sections = client.get(f"/api/v1/knowledge/{doc_id}/sections", headers=engineer_headers)
        assert sections.status_code == 200

    def test_user_cannot_write(self, client, engineer_headers):
        doc_id = self._make_doc(client)

        assert client.post(
            "/api/v1/knowledge",
            json={"title": "越权新建", "content": "x"},
            headers=engineer_headers,
        ).status_code == 403
        assert client.put(
            f"/api/v1/knowledge/{doc_id}",
            json={"title": "越权改名"},
            headers=engineer_headers,
        ).status_code == 403
        assert client.delete(
            f"/api/v1/knowledge/{doc_id}", headers=engineer_headers,
        ).status_code == 403

    def test_templates_stay_admin_only(self, client, engineer_headers):
        assert client.get("/api/v1/knowledge/templates", headers=engineer_headers).status_code == 403
