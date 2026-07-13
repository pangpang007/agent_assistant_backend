import pytest


@pytest.mark.asyncio
class TestModels:

    async def test_create_provider_openai(self, client, auth_headers):
        """添加 OpenAI 供应商"""
        response = await client.post("/api/models/providers", json={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test1234567890abcdef",
            "models": ["gpt-4o", "gpt-4o-mini"],
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["provider_name"] == "OpenAI"

    async def test_create_provider_custom(self, client, auth_headers):
        """添加自定义供应商"""
        response = await client.post("/api/models/providers", json={
            "provider_name": "My Ollama",
            "provider_type": "custom",
            "api_key": "not-needed",
            "base_url": "http://localhost:11434/v1",
            "models": ["llama3", "qwen2"],
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_create_custom_provider_without_base_url(self, client, auth_headers):
        """添加自定义供应商 - 缺少 base_url"""
        response = await client.post("/api/models/providers", json={
            "provider_name": "Bad Custom",
            "provider_type": "custom",
            "api_key": "test",
        }, headers=auth_headers)
        assert response.status_code == 422  # 或 400

    async def test_list_providers_masked_key(self, client, auth_headers):
        """获取供应商列表 - API Key 应脱敏"""
        # 先创建
        await client.post("/api/models/providers", json={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test1234567890abcdef",
        }, headers=auth_headers)

        response = await client.get("/api/models/providers", headers=auth_headers)
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) >= 1
        masked = items[0]["api_key_masked"]
        assert "****" in masked
        assert "sk-test1234567890abcdef" not in masked

    async def test_toggle_provider(self, client, auth_headers):
        """启用/禁用供应商"""
        create_resp = await client.post("/api/models/providers", json={
            "provider_name": "Test Provider",
            "provider_type": "openai",
            "api_key": "sk-test",
        }, headers=auth_headers)
        provider_id = create_resp.json()["data"]["id"]

        # 禁用
        response = await client.post(f"/api/models/providers/{provider_id}/toggle", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["is_enabled"] is False

        # 启用
        response = await client.post(f"/api/models/providers/{provider_id}/toggle", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["is_enabled"] is True

    async def test_add_model_to_provider(self, client, auth_headers):
        """添加模型到供应商"""
        create_resp = await client.post("/api/models/providers", json={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test",
            "models": ["gpt-4o"],
        }, headers=auth_headers)
        provider_id = create_resp.json()["data"]["id"]

        response = await client.post(f"/api/models/providers/{provider_id}/models", json={
            "model_name": "gpt-4-turbo",
            "display_name": "GPT-4 Turbo",
        }, headers=auth_headers)
        assert response.status_code == 200

    async def test_set_default_model(self, client, auth_headers):
        """设置默认模型"""
        create_resp = await client.post("/api/models/providers", json={
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key": "sk-test",
            "models": ["gpt-4o", "gpt-4o-mini"],
        }, headers=auth_headers)
        provider_id = create_resp.json()["data"]["id"]

        # 获取模型列表
        models_resp = await client.get(f"/api/models/providers/{provider_id}/models", headers=auth_headers)
        model_id = models_resp.json()["data"]["items"][0]["id"]

        response = await client.post(f"/api/models/{model_id}/set-default", headers=auth_headers)
        assert response.status_code == 200

    async def test_usage_stats(self, client, auth_headers):
        """用量统计 - 无数据时返回空结果"""
        response = await client.get("/api/models/usage?group_by=day", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "items" in data
        assert "summary" in data
