import pytest


@pytest.mark.asyncio
class TestLogin:
    async def test_login_success(self, client, test_user):
        response = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPass123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"

    async def test_login_wrong_password(self, client, test_user):
        response = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "WrongPass123"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_nonexistent_email(self, client):
        response = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "TestPass123"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_disabled_account(self, client, db_session, test_user):
        test_user.is_active = False
        await db_session.commit()

        response = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPass123"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"
