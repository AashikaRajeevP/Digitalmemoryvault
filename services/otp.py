import hashlib
import hmac
import secrets

OTP_LENGTH = 6
_OTP_MODULUS = 10 ** OTP_LENGTH


def generate_otp():
    return f"{secrets.randbelow(_OTP_MODULUS):0{OTP_LENGTH}d}"


def hash_otp(secret, token, otp):
    message = f"{token}:{otp}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_otp(secret, token, otp, expected_hash):
    if not otp or not expected_hash:
        return False
    return hmac.compare_digest(hash_otp(secret, token, otp), expected_hash)
