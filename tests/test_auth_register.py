import pytest


@pytest.mark.asyncio
class TestRegister:
    async def test_personal_register_success(self, client):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "MyPass123",
                "account_type": "personal",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["user"]["email"] == "newuser@example.com"
        assert data["data"]["user"]["account_type"] == "personal"
        assert data["data"]["team"] is None

    async def test_team_register_success(self, client):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "team@example.com",
                "username": "teamowner",
                "password": "MyPass123",
                "account_type": "team",
                "team_name": "My Team",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["user"]["account_type"] == "team"
        assert data["data"]["team"] is not None
        assert data["data"]["team"]["name"] == "My Team"
        assert len(data["data"]["team"]["invite_code"]) == 6

    async def test_register_duplicate_email(self, client, test_user):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "username": "anotheruser",
                "password": "MyPass123",
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    async def test_register_duplicate_username(self, client, test_user):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "another@example.com",
                "username": "testuser",
                "password": "MyPass123",
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "USERNAME_ALREADY_TAKEN"

    async def test_register_weak_password(self, client):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "weak@example.com",
                "username": "weakuser",
                "password": "weakpass",
            },
        )
        assert response.status_code == 422

    async def test_register_team_without_name(self, client):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "team2@example.com",
                "username": "teamuser2",
                "password": "MyPass123",
                "account_type": "team",
            },
        )
        assert response.status_code == 422

    async def test_register_invalid_email(self, client):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "username": "user1",
                "password": "MyPass123",
            },
        )
        assert response.status_code == 422

    async def test_register_invalid_username(self, client):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "user@example.com",
                "username": "user@name!",
                "password": "MyPass123",
            },
        )
        assert response.status_code == 422
