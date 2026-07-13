import pytest

from app.core.security import hash_password
from app.models.user import User


@pytest.mark.asyncio
class TestUsers:
    async def test_get_profile_success(self, client, auth_headers):
        response = await client.get("/api/users/profile", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["email"] == "test@example.com"
        assert data["data"]["username"] == "testuser"

    async def test_get_profile_unauthorized(self, client):
        response = await client.get("/api/users/profile")
        assert response.status_code == 401

    async def test_update_username_success(self, client, auth_headers):
        response = await client.patch(
            "/api/users/profile",
            json={"username": "newname"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["username"] == "newname"

    async def test_update_username_duplicate(self, client, auth_headers, db_session):
        other = User(
            email="other@example.com",
            username="taken",
            password_hash=hash_password("Pass1234"),
            account_type="personal",
            is_active=True,
        )
        db_session.add(other)
        await db_session.commit()

        response = await client.patch(
            "/api/users/profile",
            json={"username": "taken"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    async def test_update_no_fields(self, client, auth_headers):
        response = await client.patch(
            "/api/users/profile",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 400

    async def test_change_password_success(self, client, auth_headers):
        response = await client.post(
            "/api/users/profile/change-password",
            json={
                "old_password": "TestPass123",
                "new_password": "NewPass456",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_change_password_wrong_old(self, client, auth_headers):
        response = await client.post(
            "/api/users/profile/change-password",
            json={
                "old_password": "WrongOld123",
                "new_password": "NewPass456",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_OLD_PASSWORD"

    async def test_change_password_same(self, client, auth_headers):
        response = await client.post(
            "/api/users/profile/change-password",
            json={
                "old_password": "TestPass123",
                "new_password": "TestPass123",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "SAME_PASSWORD"
