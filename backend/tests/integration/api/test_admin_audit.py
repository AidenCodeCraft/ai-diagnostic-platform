"""管理后台操作审计记录与查询。"""


class TestAdminAudit:
    def test_user_create_is_audited_without_secrets(self, client, admin_headers):
        created = client.post(
            "/api/v1/users",
            json={
                "username": "audit_user",
                "password": "Str0ng!Passw0rd",
                "role": "user",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text

        logs = client.get("/api/v1/admin/audit-logs", headers=admin_headers).json()
        assert logs["total"] >= 1
        entry = next(i for i in logs["items"] if i["action"] == "user.create")
        assert entry["operator_name"] == "admin"
        assert entry["target_type"] == "user"
        assert entry["target_id"] == str(created.json()["id"])
        assert entry["result"] == "success"
        # 审计详情不得包含密码
        assert "Str0ng" not in (entry["detail"] or "")

    def test_audit_logs_require_admin(self, anon_client, client, engineer_headers):
        assert anon_client.get("/api/v1/admin/audit-logs").status_code == 401
        assert client.get(
            "/api/v1/admin/audit-logs", headers=engineer_headers,
        ).status_code == 403

    def test_user_update_and_delete_are_audited(self, client, admin_headers):
        created = client.post(
            "/api/v1/users",
            json={
                "username": "audit_target",
                "password": "Str0ng!Passw0rd",
                "role": "user",
                "is_active": True,
            },
            headers=admin_headers,
        )
        uid = created.json()["id"]

        assert client.put(
            f"/api/v1/users/{uid}", json={"role": "engineer"}, headers=admin_headers,
        ).status_code == 200

        logs = client.get("/api/v1/admin/audit-logs", headers=admin_headers).json()
        actions = [i["action"] for i in logs["items"]]
        assert "user.update" in actions

    def test_config_save_is_audited(self, client, admin_headers, tmp_path, monkeypatch):
        import app.api.admin as admin_module

        monkeypatch.setattr(admin_module, "CONFIG_FILE", str(tmp_path / "system_config.json"))

        resp = client.put(
            "/api/v1/admin/config/system",
            json={"max_upload_mb": 111},
            headers=admin_headers,
        )
        assert resp.status_code == 200

        logs = client.get("/api/v1/admin/audit-logs", headers=admin_headers).json()
        entry = next(i for i in logs["items"] if i["action"] == "config.system.save")
        assert entry["target_type"] == "system_config"
        assert "max_upload_mb" in (entry["detail"] or "")
