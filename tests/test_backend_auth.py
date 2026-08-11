"""Tests for the M1 auth domain (login/logout/me/refresh)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


def _client(tmp_path):
    settings = Settings(platform_db_path=str(tmp_path / "platform.db"))
    return TestClient(create_app(settings))


DEMO_USER = {
    "email": "student@demo.com",
    "password": "student",
    "name": "Amira Rahman",
    "initials": "AR",
    "role": "student",
}


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #


def test_login_succeeds_for_demo_user(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/auth/login", json=DEMO_USER)

    assert response.status_code == 200
    session = response.json()["session"]
    assert session["access_token"]
    assert session["refresh_token"]
    assert isinstance(session["expires_at"], int)
    user = session["user"]
    assert user["email"] == DEMO_USER["email"]
    assert user["name"] == DEMO_USER["name"]
    assert user["initials"] == DEMO_USER["initials"]
    assert user["role"] == DEMO_USER["role"]


def test_login_wrong_password_returns_401(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/auth/login", json={"email": DEMO_USER["email"], "password": "wrong"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_email_returns_same_401(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "x"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


# --------------------------------------------------------------------------- #
# /auth/me
# --------------------------------------------------------------------------- #


def _access_token(client: TestClient) -> str:
    response = client.post("/auth/login", json=DEMO_USER)
    return response.json()["session"]["access_token"]


def test_me_returns_user_with_valid_token(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _access_token(client)
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == DEMO_USER["email"]


def test_me_returns_null_without_token(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["user"] is None


def test_me_returns_401_for_invalid_token(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})

    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Logout / refresh
# --------------------------------------------------------------------------- #


def test_logout_revokes_session(tmp_path) -> None:
    with _client(tmp_path) as client:
        token = _access_token(client)
        logout = client.post(
            "/auth/logout", headers={"Authorization": f"Bearer {token}"}
        )
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert logout.status_code == 204
    assert me.status_code == 401


def test_logout_without_token_is_noop(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/auth/logout")

    assert response.status_code == 204


def test_refresh_rotates_session(tmp_path) -> None:
    with _client(tmp_path) as client:
        login = client.post("/auth/login", json=DEMO_USER).json()["session"]
        refreshed = client.post(
            "/auth/refresh", json={"refresh_token": login["refresh_token"]}
        )
        new_token = refreshed.json()["session"]["access_token"]
        me_new = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {new_token}"}
        )
        me_old = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"}
        )

    assert refreshed.status_code == 200
    assert new_token != login["access_token"]
    assert me_new.status_code == 200
    assert me_old.status_code == 401


def test_refresh_rejects_invalid_refresh_token(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/auth/refresh", json={"refresh_token": "garbage"})

    assert response.status_code == 401


def test_refresh_token_is_single_use(tmp_path) -> None:
    with _client(tmp_path) as client:
        login = client.post("/auth/login", json=DEMO_USER).json()["session"]
        first = client.post(
            "/auth/refresh", json={"refresh_token": login["refresh_token"]}
        )
        second = client.post(
            "/auth/refresh", json={"refresh_token": login["refresh_token"]}
        )

    assert first.status_code == 200
    assert second.status_code == 401


def test_seeded_demo_users_match_frontend_mock(tmp_path) -> None:
    expected = {
        "student@demo.com": ("student", "student", "Amira Rahman", "AR"),
        "reviewer@demo.com": ("reviewer", "reviewer", "Noor Patel", "NP"),
        "admin@demo.com": ("admin", "admin", "Kenji Ito", "KI"),
    }
    with _client(tmp_path) as client:
        for email, (password, role, name, initials) in expected.items():
            response = client.post(
                "/auth/login", json={"email": email, "password": password}
            )
            assert response.status_code == 200, email
            user = response.json()["session"]["user"]
            assert user["role"] == role
            assert user["name"] == name
            assert user["initials"] == initials
