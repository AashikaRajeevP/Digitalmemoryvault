from services.security import hash_password


def make_user(
    app_module,
    username="alice",
    email="alice@example.com",
    password="password1234",
    email_verified=True,
):
    with app_module.app.app_context():
        user = app_module.User(
            username=username,
            password=hash_password(password),
            email=email,
            email_verified=email_verified,
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        return user.uid


def login(client, email="alice@example.com", password="password1234"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
    )


def test_signup_stores_normalized_email(client, app_module, sent_emails):
    response = client.post(
        "/signup",
        data={
            "password": "password1234",
            "email": "  Alice@Example.COM ",
        },
    )

    assert response.status_code == 302

    with app_module.app.app_context():
        challenge = app_module.EmailVerification.query.filter_by(
            email="alice@example.com"
        ).one()
        assert challenge.email == "alice@example.com"
        assert challenge.username == "user:alice@example.com"

    client.post("/signup/verify", data={"otp": sent_emails[-1][1]})

    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email="alice@example.com").one()
        assert user.email == "alice@example.com"
        assert user.username == "user:alice@example.com"


def test_signup_requires_email(client, app_module):
    response = client.post(
        "/signup",
        data={"password": "password1234"},
    )

    assert response.status_code == 400
    assert b"valid email" in response.data

    with app_module.app.app_context():
        assert app_module.User.query.count() == 0
        assert app_module.EmailVerification.query.count() == 0


def test_signup_rejects_invalid_email(client, app_module):
    response = client.post(
        "/signup",
        data={
            "password": "password1234",
            "email": "not-an-email",
        },
    )

    assert response.status_code == 400
    assert b"valid email" in response.data

    with app_module.app.app_context():
        assert app_module.EmailVerification.query.count() == 0


def test_signup_rejects_email_already_registered(client, app_module):
    make_user(app_module, email="shared@example.com")

    response = client.post(
        "/signup",
        data={
            "password": "password1234",
            "email": "shared@example.com",
        },
    )

    assert response.status_code == 400
    assert b"already in use" in response.data


def test_signup_rejects_registered_email_case_insensitively(client, app_module):
    make_user(app_module, email="shared@example.com")

    response = client.post(
        "/signup",
        data={
            "password": "password1234",
            "email": "SHARED@example.com",
        },
    )

    assert response.status_code == 400


def test_verified_user_can_login(client, app_module):
    make_user(app_module)

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


def test_account_page_does_not_show_username(client, app_module):
    make_user(app_module, email="alice@example.com")
    login(client)

    response = client.get("/account")

    assert response.status_code == 200
    assert b"Username:" not in response.data


def test_account_page_allows_updating_email(client, app_module):
    make_user(app_module, email="old@example.com")
    login(client, email="old@example.com")

    response = client.post("/account", data={"email": "new@example.com"})

    assert response.status_code == 302

    with app_module.app.app_context():
        assert (
            app_module.User.query.filter_by(username="alice").one().email
            == "new@example.com"
        )


def test_account_update_normalizes_email(client, app_module):
    make_user(app_module, email="old@example.com")
    login(client, email="old@example.com")

    client.post("/account", data={"email": "  Mixed@Example.COM "})

    with app_module.app.app_context():
        assert (
            app_module.User.query.filter_by(username="alice").one().email
            == "mixed@example.com"
        )


def test_account_update_rejects_invalid_email(client, app_module):
    make_user(app_module, email="old@example.com")
    login(client, email="old@example.com")

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
    login(client, email="bob@example.com")

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
    login(client, email="bob@example.com")

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
