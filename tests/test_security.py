import re
from datetime import date

from werkzeug.security import check_password_hash

from services.security import hash_password, is_password_hash


def create_user(app_module, username="alice", password="password1234", hashed=True):
    with app_module.app.app_context():
        user = app_module.User(
            username=username,
            password=hash_password(password) if hashed else password,
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        return user.uid


def create_memory(app_module, user_id, title="A memory", open_date=None):
    with app_module.app.app_context():
        memory = app_module.Memory(
            title=title,
            message="A private memory message.",
            open_date=open_date or date.today(),
            created_on=date.today(),
            user_id=user_id,
        )
        app_module.db.session.add(memory)
        app_module.db.session.commit()
        return memory.mid


def csrf_token_from(response):
    match = re.search(
        r'name="csrf_token" value="([^"]+)"',
        response.get_data(as_text=True),
    )
    assert match is not None
    return match.group(1)


def test_signup_hashes_password(client, app_module):
    response = client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "password1234",
            "email": "alice@example.com",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with app_module.app.app_context():
        user = app_module.User.query.filter_by(username="alice").one()
        assert user.password != "password1234"
        assert is_password_hash(user.password)
        assert check_password_hash(user.password, "password1234")


def test_signup_rejects_duplicate_username(client, app_module):
    first = client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "password1234",
            "email": "alice@example.com",
        },
    )
    second = client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "password1234",
            "email": "alice2@example.com",
        },
    )

    assert first.status_code == 302
    assert second.status_code == 400

    with app_module.app.app_context():
        assert app_module.User.query.filter_by(username="alice").count() == 1


def test_password_minimum_length_default_is_12(app):
    assert app.config["PASSWORD_MIN_LENGTH"] == 12


def test_signup_enforces_minimum_password_length(client):
    response = client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "x" * 11,
            "email": "alice@example.com",
        },
    )

    assert response.status_code == 400
    assert b"at least 12" in response.data


def test_public_pages_render(client):
    for path in ("/", "/login", "/signup"):
        assert client.get(path).status_code == 200


def test_authenticated_pages_render(client, app_module):
    uid = create_user(app_module)
    mid = create_memory(app_module, uid)
    client.post(
        "/login",
        data={"username": "alice", "password": "password1234"},
    )

    for path in ("/", "/create_memory", "/my_memories", f"/memory_detail/{mid}"):
        assert client.get(path).status_code == 200


def test_login_works_with_hashed_password(client, app_module):
    uid = create_user(app_module)

    response = client.post(
        "/login",
        data={"username": "alice", "password": "password1234"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    with client.session_transaction() as session:
        assert session["user_id"] == uid


def test_legacy_plaintext_password_is_upgraded_on_login(client, app_module):
    uid = create_user(app_module, hashed=False)

    response = client.post(
        "/login",
        data={"username": "alice", "password": "password1234"},
    )

    assert response.status_code == 302

    with app_module.app.app_context():
        user = app_module.db.session.get(app_module.User, uid)
        assert is_password_hash(user.password)
        assert check_password_hash(user.password, "password1234")


def test_invalid_login_uses_generic_error(client, app_module):
    create_user(app_module)

    wrong_password = client.post(
        "/login",
        data={"username": "alice", "password": "wrong-password"},
    )
    unknown_user = client.post(
        "/login",
        data={"username": "nobody", "password": "wrong-password"},
    )

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert b"Invalid username or password" in wrong_password.data
    assert b"Invalid username or password" in unknown_user.data


def test_memory_detail_requires_login(client, app_module):
    uid = create_user(app_module)
    mid = create_memory(app_module, uid)

    response = client.get(f"/memory_detail/{mid}")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_memory_detail_is_owner_only(client, app_module):
    alice_id = create_user(app_module, username="alice")
    create_user(app_module, username="bob")
    mid = create_memory(app_module, alice_id)

    client.post(
        "/login",
        data={"username": "bob", "password": "password1234"},
    )
    response = client.get(f"/memory_detail/{mid}")
    assert response.status_code == 404

    client.post("/logout")
    client.post(
        "/login",
        data={"username": "alice", "password": "password1234"},
    )
    response = client.get(f"/memory_detail/{mid}")
    assert response.status_code == 200


def test_create_memory_rejects_invalid_date(client, app_module):
    create_user(app_module)
    client.post(
        "/login",
        data={"username": "alice", "password": "password1234"},
    )

    response = client.post(
        "/create_memory",
        data={"title": "Title", "message": "Message", "open_date": "not-a-date"},
    )

    assert response.status_code == 400

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0


def test_test_route_is_removed(client):
    response = client.get("/test")

    assert response.status_code == 404


def test_security_headers_are_present(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "microphone=(self)" in response.headers["Permissions-Policy"]
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_auth_pages_are_noindex_and_same_origin(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert response.headers["Referrer-Policy"] == "same-origin"


def test_https_login_csrf_requires_same_origin_referer(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    assert app.config["WTF_CSRF_SSL_STRICT"] is True

    base_url = "https://vault.example.com"
    response = client.get("/login", base_url=base_url)
    assert response.status_code == 200
    assert response.headers["Referrer-Policy"] == "same-origin"
    token = csrf_token_from(response)

    missing_referer = client.post(
        "/login",
        base_url=base_url,
        data={
            "csrf_token": token,
            "username": "nobody",
            "password": "password1234",
        },
    )
    assert missing_referer.status_code == 400

    same_origin_referer = client.post(
        "/login",
        base_url=base_url,
        headers={"Referer": f"{base_url}/login"},
        data={
            "csrf_token": token,
            "username": "nobody",
            "password": "password1234",
        },
    )
    assert same_origin_referer.status_code == 401
    assert b"Invalid username or password" in same_origin_referer.data


def test_https_signup_csrf_requires_same_origin_referer(client, app, app_module):
    app.config["WTF_CSRF_ENABLED"] = True

    base_url = "https://vault.example.com"
    response = client.get("/signup", base_url=base_url)
    assert response.status_code == 200
    assert response.headers["Referrer-Policy"] == "same-origin"
    token = csrf_token_from(response)

    missing_referer = client.post(
        "/signup",
        base_url=base_url,
        data={
            "csrf_token": token,
            "username": "https-user",
            "password": "password1234",
            "email": "https-user@example.com",
        },
    )
    assert missing_referer.status_code == 400

    same_origin_referer = client.post(
        "/signup",
        base_url=base_url,
        headers={"Referer": f"{base_url}/signup"},
        data={
            "csrf_token": token,
            "username": "https-user",
            "password": "password1234",
            "email": "https-user@example.com",
        },
    )
    assert same_origin_referer.status_code == 302

    with app_module.app.app_context():
        assert app_module.User.query.filter_by(username="https-user").one()


def test_logout_requires_post(client, app_module):
    create_user(app_module)
    client.post(
        "/login",
        data={"username": "alice", "password": "password1234"},
    )

    assert client.get("/logout").status_code == 405

    response = client.post("/logout")
    assert response.status_code == 302

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_csrf_is_required_for_signup(client, app):
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "password1234",
            "email": "alice@example.com",
        },
    )

    assert response.status_code == 400
