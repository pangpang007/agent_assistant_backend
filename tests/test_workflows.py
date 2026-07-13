import pytest


@pytest.mark.asyncio
class TestWorkflows:
    async def test_create_and_list(self, client, auth_headers):
        create = await client.post(
            "/api/workflows",
            json={"name": "测试工作流", "description": "desc"},
            headers=auth_headers,
        )
        assert create.status_code == 200
        wf_id = create.json()["data"]["id"]
        assert create.json()["data"]["current_version"] == 1

        listing = await client.get("/api/workflows", headers=auth_headers)
        assert listing.status_code == 200
        assert listing.json()["data"]["total"] >= 1

        detail = await client.get(f"/api/workflows/{wf_id}", headers=auth_headers)
        assert detail.status_code == 200
        assert detail.json()["data"]["name"] == "测试工作流"

    async def test_update_creates_version(self, client, auth_headers):
        create = await client.post(
            "/api/workflows",
            json={"name": "Version Test"},
            headers=auth_headers,
        )
        wf_id = create.json()["data"]["id"]
        nodes = [
            {"id": "start_1", "type": "startNode", "data": {"label": "开始"}},
        ]
        update = await client.put(
            f"/api/workflows/{wf_id}",
            json={"nodes_data": nodes},
            headers=auth_headers,
        )
        assert update.status_code == 200
        assert update.json()["data"]["current_version"] == 2

    async def test_delete_workflow(self, client, auth_headers):
        create = await client.post(
            "/api/workflows",
            json={"name": "To Delete"},
            headers=auth_headers,
        )
        wf_id = create.json()["data"]["id"]
        delete = await client.delete(f"/api/workflows/{wf_id}", headers=auth_headers)
        assert delete.status_code == 200
        detail = await client.get(f"/api/workflows/{wf_id}", headers=auth_headers)
        assert detail.status_code == 404
