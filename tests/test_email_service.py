import logging

import resend

import services.email as email_service


def test_disabled_returns_true_without_sending(app, monkeypatch):
    calls = []

    def fake_send(payload):
        calls.append(payload)
        return {"id": "x"}

    monkeypatch.setattr(resend.Emails, "send", fake_send)
    app.config["TESTING"] = True
    app.config["RESEND_ENABLED"] = False

    with app.app_context():
        assert email_service.send_otp_email("user@example.com", "123456") is True

    assert calls == []


def test_testing_mode_skips_sending(app, monkeypatch):
    calls = []
    monkeypatch.setattr(resend.Emails, "send", lambda payload: calls.append(payload))
    app.config["TESTING"] = True
    app.config["RESEND_ENABLED"] = True

    with app.app_context():
        assert email_service.send_otp_email("user@example.com", "123456") is True

    assert calls == []


def test_sends_via_resend_when_enabled(app, monkeypatch):
    captured = {}

    def fake_send(payload):
        captured.update(payload)
        return {"id": "x"}

    monkeypatch.setattr(resend.Emails, "send", fake_send)
    app.config["TESTING"] = False
    app.config["RESEND_ENABLED"] = True
    app.config["RESEND_API_KEY"] = "test-key"
    app.config["RESEND_FROM_EMAIL"] = "onboarding@resend.dev"
    app.config["OTP_TTL_SECONDS"] = 300

    with app.app_context():
        assert email_service.send_otp_email("user@example.com", "654321") is True

    assert captured["from"] == "onboarding@resend.dev"
    assert captured["to"] == ["user@example.com"]
    assert "654321" in captured["text"]
    assert "5 minutes" in captured["text"]


def test_failure_returns_false_and_does_not_log_otp(app, monkeypatch, caplog):
    def boom(payload):
        raise RuntimeError("provider down 654321")

    monkeypatch.setattr(resend.Emails, "send", boom)
    app.config["TESTING"] = False
    app.config["RESEND_ENABLED"] = True
    app.config["RESEND_API_KEY"] = "test-key"
    app.config["RESEND_FROM_EMAIL"] = "onboarding@resend.dev"

    with caplog.at_level(logging.ERROR):
        with app.app_context():
            assert email_service.send_otp_email("user@example.com", "654321") is False

    assert "654321" not in caplog.text
    assert "Failed to send verification email" in caplog.text
