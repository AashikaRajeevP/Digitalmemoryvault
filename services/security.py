from hmac import compare_digest

from werkzeug.security import check_password_hash, generate_password_hash

HASH_PREFIXES = ("scrypt:", "pbkdf2:", "argon2:")
DUMMY_PASSWORD_HASH = generate_password_hash("digital-memory-vault-dummy")


def is_password_hash(value):
    return isinstance(value, str) and value.startswith(HASH_PREFIXES)


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored, candidate):
    if not candidate:
        return False
    if is_password_hash(stored):
        return check_password_hash(stored, candidate)
    return compare_digest(
        (stored or "").encode("utf-8"),
        candidate.encode("utf-8"),
    )
