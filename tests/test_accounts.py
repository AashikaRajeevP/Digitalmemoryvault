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


def test_signup_creates_user_immediately_with_normalized_email(
    client, app_module, sent_emails
):
    response = client.post(
        "/signup",
        data={
            "password": "password1234",
            "email": "  Alice@Example.COM ",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert sent_emails == []

    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email="alice@example.com").one()
        assert user.email == "alice@example.com"
        assert user.username == "user:alice@example.com"
        assert user.email_verified is False
        assert app_module.EmailVerification.query.count() == 0


def test_new_unverified_account_can_login(client, app_module):
    client.post(
        "/signup",
        data={"password": "password1234", "email": "alice@example.com"},
    )

    response = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "password1234"},
    )

    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "user_id" in session


def test_signup_requires_email(client, app_module):
    response = client.post(
        "/signup",
        data={"password": "password1234"},
    )

    assert response.status_code == 400
    assert b"valid email" in response.data

    with app_module.app.app_context():
        assert app_module.User.query.count() == 0


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
        assert app_module.User.query.count() == 0


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
