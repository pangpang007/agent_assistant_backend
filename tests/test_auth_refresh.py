import pytest

from app.core.security import create_refresh_token


@pytest.mark.asyncio
class TestRefresh:
    async def test_refresh_success(self, client, test_user):
        refresh_token, _ = create_refresh_token(
            user_id=str(test_user.id),
            email=test_user.email,
            account_type=test_user.account_type,
            team_id=None,
            username=test_user.username,
        )
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()["data"]
        assert "refresh_token" in response.json()["data"]
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    async def test_refresh_with_access_token(self, client, auth_headers):
        token = auth_headers["Authorization"].replace("Bearer ", "")
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": token},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_TOKEN_TYPE"

    async def test_refresh_invalid_token(self, client):
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )
        assert response.status_code == 401
