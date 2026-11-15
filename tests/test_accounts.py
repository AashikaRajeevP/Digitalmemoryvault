from services.security import hash_password


def make_user(app_module, username="alice", email=None, password="password1234"):
    with app_module.app.app_context():
        user = app_module.User(
            username=username,
            password=hash_password(password),
            email=email,
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        return user.uid


def login(client, username="alice", password="password1234"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
    )


def test_signup_stores_normalized_email(client, app_module):
    response = client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "password1234",
            "email": "  Alice@Example.COM ",
        },
    )

    assert response.status_code == 302

    with app_module.app.app_context():
        user = app_module.User.query.filter_by(username="alice").one()
        assert user.email == "alice@example.com"


def test_signup_requires_email(client, app_module):
    response = client.post(
        "/signup",
        data={"username": "alice", "password": "password1234"},
    )

    assert response.status_code == 400
    assert b"valid email" in response.data

    with app_module.app.app_context():
        assert app_module.User.query.count() == 0


def test_signup_rejects_invalid_email(client, app_module):
    response = client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "password1234",
            "email": "not-an-email",
        },
    )

    assert response.status_code == 400
    assert b"valid email" in response.data

    with app_module.app.app_context():
        assert app_module.User.query.count() == 0


def test_signup_rejects_duplicate_email(client, app_module):
    first = client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "password1234",
            "email": "shared@example.com",
        },
    )
    second = client.post(
        "/signup",
        data={
            "username": "bob",
            "password": "password1234",
            "email": "shared@example.com",
        },
    )

    assert first.status_code == 302
    assert second.status_code == 400
    assert b"already in use" in second.data

    with app_module.app.app_context():
        assert app_module.User.query.count() == 1


def test_signup_rejects_duplicate_email_case_insensitively(client, app_module):
    client.post(
        "/signup",
        data={
            "username": "alice",
            "password": "password1234",
            "email": "shared@example.com",
        },
    )
    second = client.post(
        "/signup",
        data={
            "username": "bob",
            "password": "password1234",
            "email": "SHARED@example.com",
        },
    )

    assert second.status_code == 400


def test_existing_accounts_without_email_still_work(client, app_module):
    make_user(app_module, email=None)

    response = login(client)

    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "user_id" in session


def test_account_requires_login(client):
    response = client.get("/account")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_account_page_shows_current_email(client, app_module):
    make_user(app_module, email="alice@example.com")
    login(client)

    response = client.get("/account")

    assert response.status_code == 200
    assert b"alice@example.com" in response.data


def test_account_page_allows_adding_email(client, app_module):
    make_user(app_module, email=None)
    login(client)

    response = client.post("/account", data={"email": "new@example.com"})

    assert response.status_code == 302

    with app_module.app.app_context():
        assert (
            app_module.User.query.filter_by(username="alice").one().email
            == "new@example.com"
        )


def test_account_update_normalizes_email(client, app_module):
    make_user(app_module, email=None)
    login(client)

    client.post("/account", data={"email": "  Mixed@Example.COM "})

    with app_module.app.app_context():
        assert (
            app_module.User.query.filter_by(username="alice").one().email
            == "mixed@example.com"
        )


def test_account_update_rejects_invalid_email(client, app_module):
    make_user(app_module, email="old@example.com")
    login(client)

    response = client.post("/account", data={"email": "bad-email"})

    assert response.status_code == 400

    with app_module.app.app_context():
        assert (
            app_module.User.query.filter_by(username="alice").one().email
            == "old@example.com"
        )


def test_account_update_rejects_email_used_by_another_user(client, app_module):
    make_user(app_module, username="alice", email="alice@example.com")
    make_user(app_module, username="bob", email="bob@example.com")
    login(client, username="bob")

    response = client.post("/account", data={"email": "alice@example.com"})

    assert response.status_code == 400

    with app_module.app.app_context():
        assert (
            app_module.User.query.filter_by(username="bob").one().email
            == "bob@example.com"
        )


def test_account_update_keeps_own_email(client, app_module):
    make_user(app_module, email="alice@example.com")
    login(client)

    response = client.post("/account", data={"email": "alice@example.com"})

    assert response.status_code == 302

    with app_module.app.app_context():
        assert (
            app_module.User.query.filter_by(username="alice").one().email
            == "alice@example.com"
        )


def test_account_only_updates_logged_in_user(client, app_module):
    make_user(app_module, username="alice", email="alice@example.com")
    make_user(app_module, username="bob", email="bob@example.com")
    login(client, username="bob")

    client.post("/account", data={"email": "bob-new@example.com"})

    with app_module.app.app_context():
        assert (
            app_module.User.query.filter_by(username="alice").one().email
            == "alice@example.com"
        )
        assert (
            app_module.User.query.filter_by(username="bob").one().email
            == "bob-new@example.com"
        )


def test_account_update_requires_csrf(client, app):
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post("/account", data={"email": "x@example.com"})

    assert response.status_code == 400
