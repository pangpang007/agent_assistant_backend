import pytest


@pytest.mark.asyncio
class TestVectorSearch:

    async def test_search_empty_kb(self, client, auth_headers):
        """检索空知识库"""
        kb_resp = await client.post("/api/knowledge", json={
            "name": "检索测试",
        }, headers=auth_headers)
        kb_id = kb_resp.json()["data"]["id"]

        response = await client.post(
            f"/api/knowledge/{kb_id}/search",
            json={"query": "测试查询", "top_k": 5},
            headers=auth_headers,
        )
        # 空知识库可能返回空结果或 NO_READY_DOCUMENTS 错误
        assert response.status_code in (200, 400)

    async def test_search_after_document(self, client, auth_headers):
        """上传文档后检索（需要真实的 Embedding API）"""
        # 这是一个集成测试，需要配置有效的 Embedding API Key
        # 在 CI 中应标记为 @pytest.mark.integration
        pass
