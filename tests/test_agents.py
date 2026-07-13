import pytest


@pytest.mark.asyncio
class TestAgents:

    async def test_list_agents_empty(self, client, auth_headers):
        """新用户获取 Agent 列表 - 仅返回预置 Agent"""
        response = await client.get("/api/agents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 6  # 6 个预置 Agent
        assert all(item["is_preset"] for item in data["items"])

    async def test_create_agent_success(self, client, auth_headers):
        """创建自定义 Agent"""
        response = await client.post("/api/agents", json={
            "name": "我的 Agent",
            "description": "测试用 Agent",
            "system_prompt": "You are a helpful assistant.",
            "temperature": 0.5,
            "max_tokens": 2048,
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "我的 Agent"

    async def test_create_agent_with_tools(self, client, auth_headers):
        """创建 Agent 并挂载工具"""
        # 先获取预置工具列表
        tools_resp = await client.get("/api/tools", headers=auth_headers)
        tool_ids = [t["id"] for t in tools_resp.json()["data"]["items"][:2]]

        response = await client.post("/api/agents", json={
            "name": "带工具的 Agent",
            "tool_ids": tool_ids,
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_get_preset_agent_detail(self, client, auth_headers):
        """查看预置 Agent 详情"""
        list_resp = await client.get("/api/agents?is_preset=true", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.get(f"/api/agents/{preset_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["is_preset"] is True

    async def test_update_preset_agent_forbidden(self, client, auth_headers):
        """修改预置 Agent - 应被拒绝"""
        list_resp = await client.get("/api/agents?is_preset=true", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.put(f"/api/agents/{preset_id}", json={
            "name": "Modified",
        }, headers=auth_headers)
        assert response.status_code == 403

    async def test_delete_preset_agent_forbidden(self, client, auth_headers):
        """删除预置 Agent - 应被拒绝"""
        list_resp = await client.get("/api/agents?is_preset=true", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.delete(f"/api/agents/{preset_id}", headers=auth_headers)
        assert response.status_code == 403

    async def test_copy_preset_agent(self, client, auth_headers):
        """复制预置 Agent 为自定义"""
        list_resp = await client.get("/api/agents?is_preset=true", headers=auth_headers)
        preset_id = list_resp.json()["data"]["items"][0]["id"]

        response = await client.post(f"/api/agents/{preset_id}/copy", json={
            "name": "我的产品经理",
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "我的产品经理"
        assert data["original_id"] == str(preset_id)

    async def test_update_custom_agent(self, client, auth_headers):
        """更新自定义 Agent"""
        # 先创建
        create_resp = await client.post("/api/agents", json={
            "name": "Test Agent",
        }, headers=auth_headers)
        agent_id = create_resp.json()["data"]["id"]

        response = await client.put(f"/api/agents/{agent_id}", json={
            "name": "Updated Agent",
            "temperature": 0.3,
        }, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Agent"

    async def test_delete_custom_agent(self, client, auth_headers):
        """删除自定义 Agent"""
        create_resp = await client.post("/api/agents", json={
            "name": "To Delete",
        }, headers=auth_headers)
        agent_id = create_resp.json()["data"]["id"]

        response = await client.delete(f"/api/agents/{agent_id}", headers=auth_headers)
        assert response.status_code == 200

    async def test_create_agent_invalid_model(self, client, auth_headers):
        """创建 Agent - 使用无效 model_id"""
        import uuid
        fake_model_id = str(uuid.uuid4())

        response = await client.post("/api/agents", json={
            "name": "Bad Agent",
            "model_id": fake_model_id,
        }, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_MODEL_ID"
