import pytest


@pytest.mark.asyncio
class TestWorkflowImportExport:
    async def test_export_import(self, client, auth_headers):
        create = await client.post(
            "/api/workflows",
            json={
                "name": "Export WF",
                "nodes_data": [{"id": "s1", "type": "startNode", "data": {"label": "S"}}],
                "edges_data": [],
            },
            headers=auth_headers,
        )
        wf_id = create.json()["data"]["id"]

        export = await client.get(f"/api/workflows/{wf_id}/export", headers=auth_headers)
        assert export.status_code == 200
        export_data = export.json()["data"]

        imported = await client.post(
            "/api/workflows/import",
            json={"data": export_data},
            headers=auth_headers,
        )
        assert imported.status_code == 200
        assert imported.json()["data"]["name"] != "Export WF"
