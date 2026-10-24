from tests.conftest import login, make_user


def test_register_creates_agent(client):
    res = client.post(
        "/auth/register",
        json={"email": "New@Example.com", "full_name": "New User", "password": "password123"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "agent"
    assert "password" not in body and "hashed_password" not in body


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "full_name": "Dup", "password": "password123"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_register_validation(client):
    bad_email = {"email": "nope", "full_name": "X", "password": "password123"}
    short_pw = {"email": "a@example.com", "full_name": "X", "password": "short"}
    assert client.post("/auth/register", json=bad_email).status_code == 422
    assert client.post("/auth/register", json=short_pw).status_code == 422


def test_login_success_and_me(client, db_session):
    make_user(db_session, "me@example.com")
    headers = login(client, "me@example.com")
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"


def test_login_wrong_password(client, db_session):
    make_user(db_session, "me@example.com")
    res = client.post("/auth/login", data={"username": "me@example.com", "password": "wrong-pass"})
    assert res.status_code == 401


def test_protected_routes_need_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/leads").status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/leads", headers=bad).status_code == 401


def test_users_list_is_admin_only(client, agent, admin):
    assert client.get("/users", headers=agent[1]).status_code == 403
    res = client.get("/users", headers=admin[1])
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
