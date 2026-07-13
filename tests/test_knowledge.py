import pytest
import io


@pytest.mark.asyncio
class TestKnowledgeBases:

    async def test_create_kb(self, client, auth_headers):
        """创建知识库"""
        response = await client.post("/api/knowledge", json={
            "name": "测试知识库",
            "description": "用于测试",
            "chunk_size": 512,
            "chunk_overlap": 50,
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "测试知识库"
        assert data["chunk_size"] == 512

    async def test_list_kb_empty(self, client, auth_headers):
        """空知识库列表"""
        response = await client.get("/api/knowledge", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0

    async def test_get_kb_not_found(self, client, auth_headers):
        """获取不存在的知识库"""
        response = await client.get(
            "/api/knowledge/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_delete_kb(self, client, auth_headers):
        """删除知识库"""
        # 先创建
        create_resp = await client.post("/api/knowledge", json={
            "name": "待删除",
        }, headers=auth_headers)
        kb_id = create_resp.json()["data"]["id"]

        # 删除
        response = await client.delete(f"/api/knowledge/{kb_id}", headers=auth_headers)
        assert response.status_code == 200

    async def test_update_config(self, client, auth_headers):
        """更新分块配置"""
        create_resp = await client.post("/api/knowledge", json={
            "name": "配置测试",
        }, headers=auth_headers)
        kb_id = create_resp.json()["data"]["id"]

        response = await client.put(f"/api/knowledge/{kb_id}/config", json={
            "chunk_size": 1024,
            "chunk_overlap": 100,
        }, headers=auth_headers)
        assert response.status_code == 200


@pytest.mark.asyncio
class TestDocuments:

    async def test_upload_txt_document(self, client, auth_headers):
        """上传 TXT 文档"""
        # 创建知识库
        kb_resp = await client.post("/api/knowledge", json={
            "name": "文档测试",
        }, headers=auth_headers)
        kb_id = kb_resp.json()["data"]["id"]

        # 上传文档
        file_content = b"This is test content.\nSecond line."
        response = await client.post(
            f"/api/knowledge/{kb_id}/documents",
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "pending"
        assert data["file_type"] == "txt"

    async def test_upload_unsupported_type(self, client, auth_headers):
        """上传不支持的文件类型"""
        kb_resp = await client.post("/api/knowledge", json={
            "name": "类型测试",
        }, headers=auth_headers)
        kb_id = kb_resp.json()["data"]["id"]

        response = await client.post(
            f"/api/knowledge/{kb_id}/documents",
            files={"file": ("test.png", io.BytesIO(b"fake"), "image/png")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    async def test_document_list(self, client, auth_headers):
        """获取文档列表"""
        kb_resp = await client.post("/api/knowledge", json={
            "name": "列表测试",
        }, headers=auth_headers)
        kb_id = kb_resp.json()["data"]["id"]

        response = await client.get(
            f"/api/knowledge/{kb_id}/documents",
            headers=auth_headers,
        )
        assert response.status_code == 200
