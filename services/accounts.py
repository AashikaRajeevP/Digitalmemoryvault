import re

EMAIL_MAX_LENGTH = 254
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value):
    if value is None:
        return None
    return value.strip().lower()


def is_valid_email(value):
    if not isinstance(value, str):
        return False
    if not value or len(value) > EMAIL_MAX_LENGTH:
        return False
    return _EMAIL_PATTERN.match(value) is not None
