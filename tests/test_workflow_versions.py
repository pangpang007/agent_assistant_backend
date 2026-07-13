import pytest


@pytest.mark.asyncio
class TestWorkflowVersions:
    async def test_list_versions_after_create(self, client, auth_headers):
        create = await client.post(
            "/api/workflows",
            json={"name": "Version WF"},
            headers=auth_headers,
        )
        wf_id = create.json()["data"]["id"]

        versions = await client.get(
            f"/api/workflows/{wf_id}/versions", headers=auth_headers
        )
        assert versions.status_code == 200
        assert versions.json()["data"]["total"] == 1
        assert versions.json()["data"]["items"][0]["version_number"] == 1

    async def test_rollback(self, client, auth_headers):
        create = await client.post(
            "/api/workflows",
            json={"name": "Rollback WF", "nodes_data": [{"id": "a", "type": "startNode", "data": {}}]},
            headers=auth_headers,
        )
        wf_id = create.json()["data"]["id"]
        await client.put(
            f"/api/workflows/{wf_id}",
            json={"nodes_data": [{"id": "b", "type": "startNode", "data": {}}]},
            headers=auth_headers,
        )
        rollback = await client.post(
            f"/api/workflows/{wf_id}/versions/1/rollback",
            headers=auth_headers,
        )
        assert rollback.status_code == 200
        assert rollback.json()["data"]["new_version_number"] == 3
