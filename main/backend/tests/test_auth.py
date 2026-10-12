import pytest


def register(client, **overrides):
    payload = {"email": "ada@example.com", "password": "long-enough-pass", "full_name": "Ada Lovelace"}
    payload.update(overrides)
    return client.post("/auth/register", json=payload)


def test_register_returns_safe_user(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["email"] == "ada@example.com"
    assert response.json()["full_name"] == "Ada Lovelace"
    assert "hashed_password" not in response.json()
    assert "password" not in response.json()


def test_register_normalizes_email_and_rejects_duplicates(client):
    assert register(client).status_code == 201
    response = register(client, email="ADA@EXAMPLE.COM")
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "ada@example.com", "password": "short"},
        {"email": "not-an-email", "password": "long-enough-pass"},
    ],
)
def test_register_validates_email_and_password(client, payload):
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


def test_login_returns_a_valid_token(client):
    register(client)
    response = client.post("/auth/login", json={"email": "ada@example.com", "password": "long-enough-pass"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)


def test_invalid_logins_use_the_same_error(client):
    register(client)
    wrong_password = client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "incorrect-password"}
    )
    missing_user = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "incorrect-password"}
    )
    assert wrong_password.status_code == missing_user.status_code == 401
    assert wrong_password.json()["detail"] == missing_user.json()["detail"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer garbage"}])
def test_me_rejects_missing_or_invalid_tokens(client, headers):
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_me_returns_the_authenticated_user(client):
    user = register(client).json()
    token = client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "long-enough-pass"}
    ).json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == user


def test_health_remains_public(client):
    response = client.get("/health")
    assert response.status_code == 200


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_frontend_dev_origins_can_call_api(client, origin):
    response = client.options(
        "/auth/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
