from flask import current_app


def send_otp_email(to_email, otp):
    app = current_app
    if app.config.get("TESTING") or not app.config.get("RESEND_ENABLED"):
        return True

    import resend

    resend.api_key = app.config["RESEND_API_KEY"]
    ttl_minutes = max(1, app.config["OTP_TTL_SECONDS"] // 60)

    try:
        resend.Emails.send(
            {
                "from": app.config["RESEND_FROM_EMAIL"],
                "to": [to_email],
                "subject": "Your Digital Memory Vault verification code",
                "text": (
                    "Your Digital Memory Vault verification code is below. "
                    f"It expires in {ttl_minutes} minutes.\n\n{otp}\n"
                ),
            }
        )
    except Exception:
        app.logger.error("Failed to send verification email.")
        return False

    return True
