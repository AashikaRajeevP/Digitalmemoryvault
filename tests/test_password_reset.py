from datetime import datetime, timedelta, timezone

from services.otp import hash_otp, hash_token
from services.security import hash_password, is_password_hash, verify_password


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_user(
    app_module,
    email="alice@example.com",
    password="password1234",
):
    with app_module.app.app_context():
        user = app_module.User(
            username=f"user:{email}",
            password=hash_password(password),
            email=email,
            email_verified=False,
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        return user.uid


def request_reset(client, email="alice@example.com"):
    return client.post("/forgot_password", data={"email": email})


def pending_token(client):
    with client.session_transaction() as session:
        return session.get("pending_reset_token")


def reset(client, otp, password="new-password-123", confirm=None):
    return client.post(
        "/reset_password",
        data={
            "otp": otp,
            "password": password,
            "confirm_password": password if confirm is None else confirm,
        },
    )


def wrong_otp(otp):
    return "000000" if otp != "000000" else "111111"


def test_forgot_password_page_renders(client):
    response = client.get("/forgot_password")

    assert response.status_code == 200
    assert b"Send reset code" in response.data


def test_login_page_links_to_forgot_password(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b"Forgot password" in response.data


def test_forgot_password_existing_email_sends_otp(
    client, app_module, sent_emails
):
    make_user(app_module)

    response = request_reset(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reset_password")
    assert len(sent_emails) == 1
    assert sent_emails[0][0] == "alice@example.com"

    otp = sent_emails[0][1]
    assert len(otp) == 6
    assert otp.isdigit()

    token = pending_token(client)
    assert token

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        assert challenge.user_id is not None
        assert challenge.email == "alice@example.com"
        assert challenge.token_hash != token
        assert challenge.token_hash == hash_token(
            app_module.app.config["OTP_SECRET"], token
        )
        assert challenge.otp_hash != otp
        assert challenge.otp_hash == hash_otp(
            app_module.app.config["OTP_SECRET"], token, otp
        )
        assert challenge.attempts == 0
        assert challenge.used is False


def test_forgot_password_unknown_email_creates_challenge_but_sends_nothing(
    client, app_module, sent_emails
):
    response = request_reset(client, email="nobody@example.com")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reset_password")
    assert sent_emails == []

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        assert challenge.user_id is None


def test_forgot_password_does_not_reveal_registration(
    client, app_module, sent_emails
):
    make_user(app_module, email="known@example.com")

    known = client.post(
        "/forgot_password",
        data={"email": "known@example.com"},
        follow_redirects=True,
    )
    unknown = client.post(
        "/forgot_password",
        data={"email": "unknown@example.com"},
        follow_redirects=True,
    )

    assert known.status_code == 200
    assert unknown.status_code == 200
    assert b"If an account exists for that email" in known.data
    assert b"If an account exists for that email" in unknown.data
    assert len(sent_emails) == 1


def test_forgot_password_rejects_invalid_email(client, app_module, sent_emails):
    response = client.post("/forgot_password", data={"email": "not-an-email"})

    assert response.status_code == 400
    assert b"valid email" in response.data
    assert sent_emails == []

    with app_module.app.app_context():
        assert app_module.PasswordReset.query.count() == 0


def test_forgot_password_normalizes_email(client, app_module, sent_emails):
    make_user(app_module)

    request_reset(client, email="  Alice@Example.COM ")

    assert sent_emails[0][0] == "alice@example.com"

    with app_module.app.app_context():
        assert app_module.PasswordReset.query.one().email == "alice@example.com"


def test_forgot_password_invalidates_previous_challenge(
    client, app_module, sent_emails
):
    make_user(app_module)
    request_reset(client)
    first_token = pending_token(client)

    request_reset(client)

    with app_module.app.app_context():
        first = app_module.PasswordReset.query.filter_by(
            token_hash=hash_token(
                app_module.app.config["OTP_SECRET"], first_token
            )
        ).one()
        assert first.used is True
        assert app_module.PasswordReset.query.count() == 2


def test_reset_password_changes_hash_and_is_single_use(
    client, app_module, sent_emails
):
    uid = make_user(app_module)
    request_reset(client)
    otp = sent_emails[0][1]
    token = pending_token(client)

    response = reset(client, otp)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with app_module.app.app_context():
        user = app_module.db.session.get(app_module.User, uid)
        assert is_password_hash(user.password)
        assert verify_password(user.password, "new-password-123")
        assert not verify_password(user.password, "password1234")
        assert user.auth_version == 2
        challenge = app_module.PasswordReset.query.one()
        assert challenge.used is True

    with client.session_transaction() as session:
        assert "pending_reset_token" not in session
        assert "user_id" not in session

    with client.session_transaction() as session:
        session["pending_reset_token"] = token

    reuse = reset(client, otp, password="another-password-123")

    assert reuse.status_code == 302
    assert reuse.headers["Location"].endswith("/forgot_password")

    with app_module.app.app_context():
        user = app_module.db.session.get(app_module.User, uid)
        assert verify_password(user.password, "new-password-123")


def test_reset_password_wrong_otp_increments_attempts(
    client, app_module, sent_emails
):
    make_user(app_module)
    request_reset(client)

    response = reset(client, wrong_otp(sent_emails[0][1]))

    assert response.status_code == 400
    assert b"invalid or has expired" in response.data

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        assert challenge.attempts == 1
        assert challenge.used is False


def test_reset_password_attempt_limit_invalidates(
    client, app_module, sent_emails, monkeypatch
):
    monkeypatch.setitem(app_module.app.config, "OTP_MAX_ATTEMPTS", 3)
    make_user(app_module)
    request_reset(client)
    otp = wrong_otp(sent_emails[0][1])

    assert reset(client, otp).status_code == 400
    assert reset(client, otp).status_code == 400
    third = reset(client, otp)

    assert third.status_code == 302
    assert third.headers["Location"].endswith("/forgot_password")

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        assert challenge.used is True
        assert challenge.attempts == 3

    with client.session_transaction() as session:
        assert "pending_reset_token" not in session


def test_reset_password_expired_code_rejected(client, app_module, sent_emails):
    make_user(app_module)
    request_reset(client)
    otp = sent_emails[0][1]

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        challenge.expires_at = utcnow() - timedelta(seconds=1)
        app_module.db.session.commit()

    response = reset(client, otp)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/forgot_password")

    with app_module.app.app_context():
        user = app_module.User.query.one()
        assert verify_password(user.password, "password1234")


def test_reset_password_requires_pending_session(client):
    response = reset(client, "123456")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/forgot_password")


def test_reset_password_rejects_unknown_token(client):
    with client.session_transaction() as session:
        session["pending_reset_token"] = "not-a-real-token"

    response = reset(client, "123456")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/forgot_password")


def test_reset_password_unknown_email_challenge_fails(
    client, app_module
):
    request_reset(client, email="nobody@example.com")
    token = pending_token(client)
    otp = "123456"

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        challenge.otp_hash = hash_otp(
            app_module.app.config["OTP_SECRET"], token, otp
        )
        app_module.db.session.commit()

    response = reset(client, otp)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/forgot_password")


def test_reset_password_rejects_changed_email(
    client, app_module, sent_emails
):
    uid = make_user(app_module)
    request_reset(client)

    with app_module.app.app_context():
        user = app_module.db.session.get(app_module.User, uid)
        user.email = "changed@example.com"
        app_module.db.session.commit()

    response = reset(client, sent_emails[0][1])

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/forgot_password")


def test_reset_password_requires_matching_passwords(
    client, app_module, sent_emails
):
    make_user(app_module)
    request_reset(client)

    response = reset(
        client,
        sent_emails[0][1],
        password="new-password-123",
        confirm="different-password-123",
    )

    assert response.status_code == 400
    assert b"do not match" in response.data

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        assert challenge.attempts == 0
        assert challenge.used is False


def test_reset_password_enforces_minimum_length(
    client, app_module, sent_emails
):
    make_user(app_module)
    request_reset(client)

    response = reset(client, sent_emails[0][1], password="short")

    assert response.status_code == 400
    assert b"between" in response.data

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        assert challenge.attempts == 0
        assert challenge.used is False


def test_reset_resend_cooldown_enforced(
    client, app_module, sent_emails, monkeypatch
):
    monkeypatch.setitem(
        app_module.app.config, "OTP_RESEND_COOLDOWN_SECONDS", 3600
    )
    make_user(app_module)
    request_reset(client)

    response = client.post("/reset_password/resend")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reset_password")
    assert len(sent_emails) == 1


def test_reset_resend_invalidates_previous_otp(
    client, app_module, sent_emails, monkeypatch
):
    monkeypatch.setitem(app_module.app.config, "OTP_RESEND_COOLDOWN_SECONDS", 0)
    make_user(app_module)
    request_reset(client)
    first_otp = sent_emails[0][1]

    response = client.post("/reset_password/resend")

    assert response.status_code == 302
    assert len(sent_emails) == 2
    second_otp = sent_emails[1][1]
    assert second_otp != first_otp
    assert reset(client, first_otp).status_code == 400
    assert reset(client, second_otp).status_code == 302

    with app_module.app.app_context():
        user = app_module.User.query.one()
        assert verify_password(user.password, "new-password-123")


def test_reset_resend_resets_attempts(
    client, app_module, sent_emails, monkeypatch
):
    monkeypatch.setitem(app_module.app.config, "OTP_RESEND_COOLDOWN_SECONDS", 0)
    make_user(app_module)
    request_reset(client)

    reset(client, wrong_otp(sent_emails[0][1]))
    client.post("/reset_password/resend")

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        assert challenge.attempts == 0


def test_forgot_password_email_failure_consumes_challenge(
    client, app_module, failing_email
):
    make_user(app_module)

    response = request_reset(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reset_password")

    with app_module.app.app_context():
        challenge = app_module.PasswordReset.query.one()
        assert challenge.used is True


def test_reset_otp_is_never_logged(
    client, app_module, sent_emails, caplog
):
    import logging

    make_user(app_module)

    with caplog.at_level(logging.DEBUG):
        request_reset(client)

    assert sent_emails[0][1] not in caplog.text


def test_password_reset_invalidates_existing_sessions(
    client, app_module, sent_emails
):
    uid = make_user(app_module)
    login = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "password1234"},
    )
    assert login.status_code == 302

    with client.session_transaction() as session:
        old_version = session["auth_version"]

    request_reset(client)
    reset(client, sent_emails[0][1])

    with client.session_transaction() as session:
        session["user_id"] = uid
        session["auth_version"] = old_version

    response = client.get("/my_memories")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_required_rejects_stale_auth_version(client, app_module):
    uid = make_user(app_module)

    with client.session_transaction() as session:
        session["user_id"] = uid
        session["auth_version"] = 999

    response = client.get("/my_memories")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_forgot_password_requires_csrf(client, app):
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post(
        "/forgot_password", data={"email": "alice@example.com"}
    )

    assert response.status_code == 400


def test_reset_password_requires_csrf(client, app):
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post(
        "/reset_password",
        data={
            "otp": "123456",
            "password": "new-password-123",
            "confirm_password": "new-password-123",
        },
    )

    assert response.status_code == 400


def test_reset_resend_requires_csrf(client, app):
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post("/reset_password/resend")

    assert response.status_code == 400
