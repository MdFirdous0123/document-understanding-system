"""Tests for authentication endpoints."""


def test_register_new_user(client):
    """A new user can register with a unique email."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "securepassword123",
            "full_name": "New User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert "id" in data
    assert "hashed_password" not in data  # password must not be exposed


def test_register_duplicate_email(client, test_user):
    """Registering with an existing email returns HTTP 400."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "testuser@example.com", "password": "anything"},
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


def test_login_success(client, test_user):
    """Valid credentials return a JWT access token."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser@example.com", "password": "testpassword123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, test_user):
    """Wrong password returns HTTP 401."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    """Login with unknown email returns HTTP 401."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com", "password": "whatever"},
    )
    assert response.status_code == 401


def test_get_me(client, auth_headers, test_user):
    """Authenticated user can retrieve their own profile."""
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testuser@example.com"


def test_get_me_unauthenticated(client):
    """Accessing /me without a token returns HTTP 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
