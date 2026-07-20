"""Tests for Project Management (v0.5)."""

def test_create_project(client):
    resp = client.post("/api/v1/projects", json={"name": "智能座舱", "chip": "SS928", "device_type": "嵌入式"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "智能座舱"
    assert data["chip"] == "SS928"


def test_list_projects_empty(client):
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_projects(client):
    for i in range(3):
        client.post("/api/v1/projects", json={"name": f"项目{i}"})
    resp = client.get("/api/v1/projects")
    assert resp.json()["total"] == 3


def test_get_project(client):
    create = client.post("/api/v1/projects", json={"name": "网关项目"})
    resp = client.get(f"/api/v1/projects/{create.json()['id']}")
    assert resp.json()["name"] == "网关项目"


def test_get_project_404(client):
    assert client.get("/api/v1/projects/99999").status_code == 404


def test_update_project(client):
    create = client.post("/api/v1/projects", json={"name": "old"})
    resp = client.put(f"/api/v1/projects/{create.json()['id']}", json={"name": "new", "firmware": "2.0"})
    data = resp.json()
    assert data["name"] == "new"
    assert data["firmware"] == "2.0"


def test_delete_project(client):
    create = client.post("/api/v1/projects", json={"name": "删除测试"})
    pid = create.json()["id"]
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 204
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404
