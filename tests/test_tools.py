import pytest


@pytest.mark.asyncio
class TestTools:

    async def test_list_tools_preset(self, client, auth_headers):
        """获取工具列表 - 预置工具"""
        response = await client.get("/api/tools", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 7
        assert all(item["is_preset"] for item in data["items"])

    async def test_create_custom_tool(self, client, auth_headers):
        """创建自定义工具"""
        response = await client.post("/api/tools", json={
            "name": "My API Tool",
            "description": "调用我的 API",
            "api_url": "https://api.example.com/v1/action",
            "auth_type": "api_key",
            "auth_config": {
                "header_name": "X-API-Key",
                "api_key_value": "sk-test123456",
            },
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_delete_tool_without_force(self, client, auth_headers):
        """删除工具 - 有引用时不传 force 应返回引用数"""
        # 创建工具
        create_resp = await client.post("/api/tools", json={
            "name": "Tool to Delete",
            "api_url": "https://api.example.com",
        }, headers=auth_headers)
        tool_id = create_resp.json()["data"]["id"]

        # 先挂载到 Agent
        agent_resp = await client.post("/api/agents", json={
            "name": "Agent with Tool",
            "tool_ids": [tool_id],
        }, headers=auth_headers)

        # 不传 force 删除
        response = await client.delete(f"/api/tools/{tool_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted"] is False
        assert data["agent_count"] >= 1

    async def test_delete_tool_with_force(self, client, auth_headers):
        """删除工具 - force=true 强制删除"""
        create_resp = await client.post("/api/tools", json={
            "name": "Tool Force Delete",
            "api_url": "https://api.example.com",
        }, headers=auth_headers)
        tool_id = create_resp.json()["data"]["id"]

        response = await client.delete(f"/api/tools/{tool_id}?force=true", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["deleted"] is True

    async def test_delete_preset_tool_forbidden(self, client, auth_headers):
        """删除预置工具 - 应被拒绝"""
        list_resp = await client.get("/api/tools?tool_type=preset", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.delete(f"/api/tools/{preset_id}?force=true", headers=auth_headers)
        assert response.status_code == 403

    async def test_test_tool_preset(self, client, auth_headers):
        """测试预置工具 - 应返回不支持直接测试"""
        list_resp = await client.get("/api/tools?tool_type=preset", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.post(f"/api/tools/{preset_id}/test", json={
            "parameters": {"query": "test"},
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["success"] is False  # 预置工具无 api_url
