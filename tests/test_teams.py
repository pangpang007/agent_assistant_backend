import pytest

from app.core.security import create_access_token, hash_password
from app.models.user import User


@pytest.mark.asyncio
class TestTeams:
    async def test_create_team_success(self, client, auth_headers):
        response = await client.post(
            "/api/teams",
            json={"name": "My New Team"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["team"]["name"] == "My New Team"
        assert len(data["data"]["team"]["invite_code"]) == 6
        assert data["data"]["user"]["account_type"] == "team"

    async def test_create_team_already_has_team(self, client, owner_headers):
        response = await client.post(
            "/api/teams",
            json={"name": "Another Team"},
            headers=owner_headers,
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ALREADY_HAS_TEAM"

    async def test_join_team_success(self, client, db_session):
        user = User(
            email="joiner@example.com",
            username="joiner",
            password_hash=hash_password("TestPass123"),
            account_type="personal",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            account_type="personal",
            team_id=None,
            username="joiner",
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            "/api/teams/join",
            json={"invite_code": "ABC123"},
            headers=headers,
        )
        assert response.status_code == 200

    async def test_join_team_invalid_code(self, client, auth_headers):
        response = await client.post(
            "/api/teams/join",
            json={"invite_code": "ZZZZZZ"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_get_members_as_owner(self, client, owner_headers):
        response = await client.get("/api/teams/members", headers=owner_headers)
        assert response.status_code == 200
        assert response.json()["data"]["total"] >= 1

    async def test_get_members_as_member_forbidden(self, client, auth_headers):
        response = await client.get("/api/teams/members", headers=auth_headers)
        assert response.status_code == 403

    async def test_reset_invite_code(self, client, owner_headers):
        response = await client.post(
            "/api/teams/invite-code/reset",
            headers=owner_headers,
        )
        assert response.status_code == 200
        assert len(response.json()["data"]["invite_code"]) == 6

    async def test_delete_team(self, client, owner_headers):
        response = await client.delete("/api/teams", headers=owner_headers)
        assert response.status_code == 200
        assert response.json()["data"]["message"] == "团队已删除"
