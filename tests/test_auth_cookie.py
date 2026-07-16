"""Phase 8: Cookie-based JWT auth tests."""

from datetime import timedelta

import pytest

from app.core.security import create_access_token, create_refresh_token


@pytest.mark.asyncio
class TestAuthCookie:
    async def test_login_sets_cookie(self, client, test_user):
        response = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPass123"},
        )
        assert response.status_code == 200
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

        set_cookie_headers = response.headers.get_list("set-cookie")
        assert set_cookie_headers
        joined = " ".join(set_cookie_headers).lower()
        assert "httponly" in joined
        assert "samesite=lax" in joined
        assert "path=/" in joined

        # Phase A: body 仍返回 token
        assert "access_token" in response.json()["data"]

    async def test_register_sets_cookie(self, client):
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "cookieuser@example.com",
                "username": "cookieuser",
                "password": "MyPass123",
                "account_type": "personal",
            },
        )
        assert response.status_code == 200
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    async def test_protected_route_requires_cookie(self, client):
        response = await client.get("/api/users/profile")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "COOKIE_MISSING"

    async def test_protected_route_with_cookie(self, client, test_user):
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPass123"},
        )
        assert login_resp.status_code == 200

        response = await client.get("/api/users/profile")
        assert response.status_code == 200
        assert response.json()["data"]["email"] == "test@example.com"

    async def test_protected_route_with_header_compat(self, client, auth_headers):
        response = await client.get("/api/users/profile", headers=auth_headers)
        assert response.status_code == 200

    async def test_logout_clears_cookie(self, client, test_user):
        await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPass123"},
        )

        response = await client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json()["data"]["message"] == "已成功登出"

        set_cookie_headers = response.headers.get_list("set-cookie")
        joined = " ".join(set_cookie_headers).lower()
        assert "max-age=0" in joined or 'access_token=""' in joined or "access_token=;" in joined

        # 登出后受保护接口应 401
        me_resp = await client.get("/api/users/profile")
        assert me_resp.status_code == 401

    async def test_token_status(self, client, test_user):
        await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPass123"},
        )

        response = await client.get("/api/auth/token-status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["is_valid"] is True
        assert data["user_id"] is not None
        assert data["access_token_remaining_seconds"] > 0
        assert data["refresh_token_valid"] is True

    async def test_refresh_via_cookie(self, client, test_user):
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "TestPass123"},
        )
        assert login_resp.status_code == 200

        response = await client.post("/api/auth/refresh")
        assert response.status_code == 200
        assert "access_token" in response.cookies
        assert response.json()["data"]["message"] == "Token 已刷新"

    async def test_auto_refresh_near_expiry(self, client, test_user):
        """剩余有效期低于阈值时，响应应带新的 Set-Cookie。"""
        access_token, _ = create_access_token(
            user_id=str(test_user.id),
            email=test_user.email,
            account_type=test_user.account_type,
            team_id=None,
            username=test_user.username,
            expires_delta=timedelta(minutes=5),
        )
        refresh_token, _ = create_refresh_token(
            user_id=str(test_user.id),
            email=test_user.email,
            account_type=test_user.account_type,
            team_id=None,
            username=test_user.username,
        )

        client.cookies.set("access_token", access_token)
        client.cookies.set("refresh_token", refresh_token)

        response = await client.get("/api/users/profile")
        assert response.status_code == 200

        set_cookie_headers = response.headers.get_list("set-cookie")
        assert any("access_token=" in h for h in set_cookie_headers)
