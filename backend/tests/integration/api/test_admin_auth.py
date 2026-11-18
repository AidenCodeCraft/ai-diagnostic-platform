"""后台接口鉴权、角色校验与 LLM 密钥脱敏。"""


class TestAdminAuth:
    def test_admin_endpoints_require_auth(self, client):
        assert client.get("/api/v1/admin/stats").status_code == 401
        assert client.get("/api/v1/users").status_code == 401
        assert client.get("/api/v1/admin/config/llm").status_code == 401
        assert client.put("/api/v1/admin/config/llm", json={"models": []}).status_code == 401

    def test_non_admin_forbidden(self, client, engineer_headers):
        assert client.get("/api/v1/admin/stats", headers=engineer_headers).status_code == 403
        assert client.get("/api/v1/users", headers=engineer_headers).status_code == 403
        assert client.get("/api/v1/admin/config/llm", headers=engineer_headers).status_code == 403

    def test_admin_allowed(self, client, admin_headers):
        assert client.get("/api/v1/admin/stats", headers=admin_headers).status_code == 200
        users = client.get("/api/v1/users", headers=admin_headers)
        assert users.status_code == 200
        assert users.json()["total"] >= 2

    def test_chat_bootstrap_configs_require_auth_but_not_admin(self, client, engineer_headers):
        """对话页初始化依赖这两个接口，普通登录用户必须可用。"""
        assert client.get(
            "/api/v1/admin/config/llm/models", headers=engineer_headers,
        ).status_code == 200
        assert client.get(
            "/api/v1/admin/config/system", headers=engineer_headers,
        ).status_code == 200

    def test_llm_config_api_key_masked_and_preserved(self, client, admin_headers, tmp_path, monkeypatch):
        import app.api.admin as admin_module

        monkeypatch.setattr(admin_module, "CONFIG_FILE", str(tmp_path / "system_config.json"))

        secret = "sk-live-1234567890abcdef"
        put = client.put(
            "/api/v1/admin/config/llm",
            json={
                "models": [{
                    "name": "DeepSeek V4 Flash",
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                    "api_key": secret,
                }],
            },
            headers=admin_headers,
        )
        assert put.status_code == 200, put.text

        got = client.get("/api/v1/admin/config/llm", headers=admin_headers).json()
        masked = got["models"][0]["api_key"]
        assert masked != secret
        assert "****" in masked
        assert masked.endswith(secret[-4:])

        # 回传掩码再保存：不得把掩码写回配置文件
        client.put("/api/v1/admin/config/llm", json={"models": got["models"]}, headers=admin_headers)
        raw = admin_module._load_config()
        assert raw["llm"]["models"][0]["api_key"] == secret

    def test_delete_user_requires_developer(self, client, admin_headers):
        created = client.post(
            "/api/v1/users",
            json={
                "username": "victim_a",
                "password": "Str0ng!Passw0rd",
                "role": "user",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert created.status_code == 201, created.text
        uid = created.json()["id"]

        # admin 无删除权限（仅 developer 可删）
        assert client.delete(f"/api/v1/users/{uid}", headers=admin_headers).status_code == 403

    def test_developer_can_delete_user(self, client, admin_headers):
        dev = client.post(
            "/api/v1/users",
            json={
                "username": "dev_a",
                "password": "Str0ng!Passw0rd",
                "role": "developer",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert dev.status_code == 201, dev.text

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "dev_a", "password": "Str0ng!Passw0rd"},
        )
        assert login.status_code == 200, login.text
        dev_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        victim = client.post(
            "/api/v1/users",
            json={
                "username": "victim_b",
                "password": "Str0ng!Passw0rd",
                "role": "user",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert victim.status_code == 201, victim.text

        resp = client.delete(f"/api/v1/users/{victim.json()['id']}", headers=dev_headers)
        assert resp.status_code == 204
