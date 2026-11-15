from datetime import datetime, timedelta, timezone

import routes
from services.otp import hash_otp
from services.security import hash_password


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def signup(client, username="alice", email="alice@example.com", password="password1234"):
    return client.post(
        "/signup",
        data={"username": username, "email": email, "password": password},
    )


def verify(client, otp):
    return client.post("/signup/verify", data={"otp": otp})


def pending_token(client):
    with client.session_transaction() as session:
        return session.get("pending_signup_token")


def test_signup_creates_pending_challenge_not_user(client, app_module, sent_emails):
    response = signup(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signup/verify")
    assert len(sent_emails) == 1
    assert sent_emails[0][0] == "alice@example.com"

    with app_module.app.app_context():
        assert app_module.User.query.count() == 0
        challenge = app_module.EmailVerification.query.one()
        assert challenge.username == "alice"
        assert challenge.email == "alice@example.com"
        assert challenge.used is False
        assert challenge.attempts == 0


def test_signup_does_not_authenticate(client, app_module, sent_emails):
    signup(client)

    with client.session_transaction() as session:
        assert "user_id" not in session
        assert session.get("pending_signup_token")


def test_signup_otp_is_six_digits(client, sent_emails):
    signup(client)

    otp = sent_emails[0][1]
    assert len(otp) == 6
    assert otp.isdigit()


def test_signup_stores_hmac_not_plaintext_otp(client, app_module, sent_emails):
    signup(client)
    otp = sent_emails[0][1]
    token = pending_token(client)

    with app_module.app.app_context():
        challenge = app_module.EmailVerification.query.one()
        assert challenge.otp_hash != otp
        assert len(challenge.otp_hash) == 64
        expected = hash_otp(app_module.app.config["OTP_SECRET"], token, otp)
        assert challenge.otp_hash == expected


def test_signup_response_does_not_leak_otp(client, sent_emails):
    response = signup(client)
    otp = sent_emails[0][1]

    assert otp.encode() not in response.data


def test_verify_success_creates_verified_user_and_redirects_login(
    client, app_module, sent_emails
):
    signup(client)
    otp = sent_emails[0][1]

    response = verify(client, otp)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with app_module.app.app_context():
        user = app_module.User.query.one()
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.email_verified is True
        challenge = app_module.EmailVerification.query.one()
        assert challenge.used is True


def test_verify_success_does_not_authenticate(client, sent_emails):
    signup(client)
    verify(client, sent_emails[0][1])

    with client.session_transaction() as session:
        assert "user_id" not in session
        assert "pending_signup_token" not in session


def test_verify_wrong_otp_increments_attempts(client, app_module, sent_emails):
    signup(client)

    response = verify(client, "000000")

    assert response.status_code == 400

    with app_module.app.app_context():
        challenge = app_module.EmailVerification.query.one()
        assert challenge.attempts == 1
        assert challenge.used is False
        assert app_module.User.query.count() == 0


def test_verify_attempt_limit_invalidates_challenge(client, app_module, sent_emails, app):
    app.config["OTP_MAX_ATTEMPTS"] = 3
    signup(client)

    assert verify(client, "000000").status_code == 400
    assert verify(client, "000001").status_code == 400
    third = verify(client, "000002")

    assert third.status_code == 302
    assert third.headers["Location"].endswith("/signup")

    with app_module.app.app_context():
        challenge = app_module.EmailVerification.query.one()
        assert challenge.used is True
        assert challenge.attempts == 3

    with client.session_transaction() as session:
        assert "pending_signup_token" not in session


def test_verify_expired_otp_is_rejected(client, app_module, sent_emails):
    signup(client)

    with app_module.app.app_context():
        challenge = app_module.EmailVerification.query.one()
        challenge.expires_at = utcnow() - timedelta(seconds=1)
        app_module.db.session.commit()

    response = verify(client, sent_emails[0][1])

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signup")

    with app_module.app.app_context():
        assert app_module.User.query.count() == 0


def test_verify_is_single_use(client, app_module, sent_emails):
    signup(client)
    otp = sent_emails[0][1]

    assert verify(client, otp).status_code == 302

    with client.session_transaction() as session:
        session["pending_signup_token"] = pending_token_value(app_module)

    second = verify(client, otp)

    assert second.status_code == 302
    assert second.headers["Location"].endswith("/signup")

    with app_module.app.app_context():
        assert app_module.User.query.count() == 1


def pending_token_value(app_module):
    with app_module.app.app_context():
        challenge = app_module.EmailVerification.query.one()
        return challenge.token


def test_verify_requires_pending_session(client, app_module, sent_emails):
    signup(client)

    with client.session_transaction() as session:
        session.pop("pending_signup_token", None)

    response = verify(client, sent_emails[0][1])

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signup")

    with app_module.app.app_context():
        assert app_module.User.query.count() == 0


def test_verify_rejects_unknown_challenge(client, app_module):
    with client.session_transaction() as session:
        session["pending_signup_token"] = "not-a-real-token"

    response = verify(client, "123456")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signup")


def test_verify_requires_csrf(client, app, sent_emails):
    signup(client)
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post("/signup/verify", data={"otp": sent_emails[0][1]})

    assert response.status_code == 400


def test_resend_requires_pending_session(client, app_module):
    response = client.post("/signup/resend")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signup")


def test_resend_cooldown_enforced(client, app, sent_emails):
    app.config["OTP_RESEND_COOLDOWN_SECONDS"] = 3600
    signup(client)

    response = client.post("/signup/resend")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signup/verify")
    assert len(sent_emails) == 1


def test_resend_invalidates_previous_otp(client, app_module, sent_emails, app):
    app.config["OTP_RESEND_COOLDOWN_SECONDS"] = 0
    signup(client)
    first_otp = sent_emails[0][1]

    response = client.post("/signup/resend")

    assert response.status_code == 302
    assert len(sent_emails) == 2
    second_otp = sent_emails[1][1]
    assert second_otp != first_otp

    assert verify(client, first_otp).status_code == 400
    assert verify(client, second_otp).status_code == 302

    with app_module.app.app_context():
        assert app_module.User.query.count() == 1


def test_resend_resets_attempts(client, app_module, sent_emails, app):
    app.config["OTP_RESEND_COOLDOWN_SECONDS"] = 0
    signup(client)
    verify(client, "000000")

    client.post("/signup/resend")

    with app_module.app.app_context():
        challenge = app_module.EmailVerification.query.one()
        assert challenge.attempts == 0


def test_signup_email_failure_marks_challenge_used(
    client, app_module, failing_email
):
    response = signup(client)

    assert response.status_code == 502

    with app_module.app.app_context():
        assert app_module.User.query.count() == 0
        challenge = app_module.EmailVerification.query.one()
        assert challenge.used is True

    with client.session_transaction() as session:
        assert "pending_signup_token" not in session


def test_resend_email_failure_marks_challenge_used(
    client, app_module, sent_emails, app, monkeypatch
):
    app.config["OTP_RESEND_COOLDOWN_SECONDS"] = 0
    signup(client)

    monkeypatch.setattr(routes, "send_otp_email", lambda to, otp: False)
    response = client.post("/signup/resend")

    assert response.status_code == 302

    with app_module.app.app_context():
        challenge = app_module.EmailVerification.query.one()
        assert challenge.used is True


def test_otp_is_never_logged(client, sent_emails, caplog):
    import logging

    with caplog.at_level(logging.DEBUG):
        signup(client)

    otp = sent_emails[0][1]
    assert otp not in caplog.text


def test_expired_challenges_are_purged_on_signup(client, app_module, sent_emails):
    with app_module.app.app_context():
        stale = app_module.EmailVerification(
            token="stale-token",
            username="stale",
            email="stale@example.com",
            password_hash="x",
            otp_hash="y",
            attempts=0,
            used=False,
            expires_at=utcnow() - timedelta(seconds=5),
            last_sent_at=utcnow() - timedelta(seconds=5),
            created_at=utcnow() - timedelta(seconds=5),
        )
        app_module.db.session.add(stale)
        app_module.db.session.commit()

    signup(client, username="alice", email="alice@example.com")

    with app_module.app.app_context():
        assert (
            app_module.EmailVerification.query.filter_by(token="stale-token").first()
            is None
        )
        assert app_module.EmailVerification.query.count() == 1


def test_login_does_not_send_otp(client, app_module, sent_emails):
    with app_module.app.app_context():
        app_module.db.session.add(
            app_module.User(
                username="alice",
                password=hash_password("password1234"),
                email="alice@example.com",
                email_verified=True,
            )
        )
        app_module.db.session.commit()

    client.post("/login", data={"email": "alice@example.com", "password": "password1234"})

    assert sent_emails == []


def test_verify_rejects_username_taken_between_signup_and_verify(
    client, app_module, sent_emails
):
    signup(client)

    with app_module.app.app_context():
        app_module.db.session.add(
            app_module.User(
                username="alice",
                password="x",
                email="other@example.com",
                email_verified=True,
            )
        )
        app_module.db.session.commit()

    response = verify(client, sent_emails[0][1])

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with app_module.app.app_context():
        assert app_module.User.query.count() == 1
