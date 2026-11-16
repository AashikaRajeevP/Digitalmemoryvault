"""Cloudinary photo helpers.

Images are uploaded directly from the browser to Cloudinary using a short-lived
signature generated here. The application never receives image bytes and never
exposes the Cloudinary API secret to the client.
"""

import hashlib
import json
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from flask import current_app

ALLOWED_IMAGE_FORMATS = ("jpg", "jpeg", "png", "webp", "gif")
MAX_PUBLIC_ID_LENGTH = 300
MAX_URL_LENGTH = 2048


class PhotoUploadsNotConfigured(Exception):
    pass


class PhotoValidationError(Exception):
    pass


def _config():
    return {
        "cloud_name": current_app.config.get("CLOUDINARY_CLOUD_NAME", "").strip(),
        "api_key": current_app.config.get("CLOUDINARY_API_KEY", "").strip(),
        "api_secret": current_app.config.get("CLOUDINARY_API_SECRET", "").strip(),
        "folder": (
            current_app.config.get("CLOUDINARY_UPLOAD_FOLDER", "memoryvault")
            .strip()
            .strip("/")
            or "memoryvault"
        ),
    }


def is_configured():
    config = _config()
    return all(
        (config["cloud_name"], config["api_key"], config["api_secret"])
    )


def upload_folder(user_id):
    return f"{_config()['folder']}/users/{int(user_id)}"


def _sign(params):
    config = _config()
    if not config["api_secret"]:
        raise PhotoUploadsNotConfigured
    to_sign = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.sha1(
        f"{to_sign}{config['api_secret']}".encode("utf-8")
    ).hexdigest()


def build_upload_signature(user_id):
    if not is_configured():
        raise PhotoUploadsNotConfigured

    config = _config()
    params = {
        "folder": upload_folder(user_id),
        "timestamp": int(time.time()),
        "allowed_formats": ",".join(ALLOWED_IMAGE_FORMATS),
    }

    response = {
        "upload_url": (
            "https://api.cloudinary.com/v1_1/"
            f"{config['cloud_name']}/image/upload"
        ),
        "api_key": config["api_key"],
        "cloud_name": config["cloud_name"],
        "signature": _sign(params),
    }
    response.update({key: str(value) for key, value in params.items()})
    return response


def _is_allowed_secure_url(secure_url, public_id):
    if not isinstance(secure_url, str) or len(secure_url) > MAX_URL_LENGTH:
        return False

    try:
        parsed = urlparse(secure_url)
        port = parsed.port
    except ValueError:
        return False

    if parsed.scheme != "https" or parsed.hostname != "res.cloudinary.com":
        return False
    if parsed.username or parsed.password or port not in (None, 443):
        return False
    if public_id not in parsed.path or ".." in parsed.path:
        return False

    cloud_name = _config()["cloud_name"]
    return parsed.path.startswith(f"/{cloud_name}/image/upload/")


def _optional_positive_int(value):
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise PhotoValidationError("One or more photos have invalid metadata.")
    return value


def normalize_photos(raw_photos, user_id, max_photos, max_bytes):
    """Validate uploaded-photo metadata supplied by the browser.

    Only assets inside the current user's Cloudinary folder are accepted.
    The returned list is ordered and has exactly one cover photo.
    """
    if raw_photos is None or str(raw_photos).strip() == "":
        return []

    if isinstance(raw_photos, str):
        try:
            items = json.loads(raw_photos)
        except (TypeError, ValueError):
            raise PhotoValidationError(
                "One or more photos could not be verified. Please re-upload them."
            )
    else:
        items = raw_photos

    if not isinstance(items, list):
        raise PhotoValidationError(
            "One or more photos could not be verified. Please re-upload them."
        )

    if len(items) > max_photos:
        raise PhotoValidationError(
            f"You can attach up to {max_photos} photos to a memory."
        )

    if not items:
        return []

    prefix = f"{upload_folder(user_id)}/"
    seen_public_ids = set()
    normalized = []

    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise PhotoValidationError(
                "One or more photos could not be verified. Please re-upload them."
            )

        public_id = item.get("public_id")
        secure_url = item.get("secure_url")

        if (
            not isinstance(public_id, str)
            or not public_id
            or len(public_id) > MAX_PUBLIC_ID_LENGTH
            or not public_id.startswith(prefix)
            or ".." in public_id
            or "//" in public_id
            or any(character.isspace() for character in public_id)
        ):
            raise PhotoValidationError(
                "One or more photos could not be verified. Please re-upload them."
            )

        if public_id in seen_public_ids:
            raise PhotoValidationError(
                "The same photo was attached more than once. Please re-upload it."
            )
        seen_public_ids.add(public_id)

        if not _is_allowed_secure_url(secure_url, public_id):
            raise PhotoValidationError(
                "One or more photos could not be verified. Please re-upload them."
            )

        image_format = str(item.get("format") or "").strip().lower()
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise PhotoValidationError(
                "Unsupported photo type. Use JPG, PNG, WebP, or GIF."
            )

        size = item.get("bytes")
        if type(size) is not int or size <= 0 or size > max_bytes:
            max_mb = max(1, max_bytes // (1024 * 1024))
            raise PhotoValidationError(
                f"One or more photos are too large. The maximum is {max_mb} MB."
            )

        normalized.append(
            {
                "public_id": public_id,
                "secure_url": secure_url,
                "is_cover": bool(item.get("is_cover")),
                "position": position,
                "width": _optional_positive_int(item.get("width")),
                "height": _optional_positive_int(item.get("height")),
                "image_format": image_format,
                "bytes": size,
            }
        )

    cover_selected = False
    for photo in normalized:
        if photo["is_cover"] and not cover_selected:
            cover_selected = True
        else:
            photo["is_cover"] = False

    if not cover_selected:
        normalized[0]["is_cover"] = True

    return normalized


def extract_user_public_ids(raw_photos, user_id, limit=50):
    """Return user-owned public IDs from a raw payload for best-effort cleanup."""
    try:
        items = json.loads(raw_photos) if isinstance(raw_photos, str) else raw_photos
    except (TypeError, ValueError):
        return []

    if not isinstance(items, list):
        return []

    prefix = f"{upload_folder(user_id)}/"
    public_ids = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        public_id = item.get("public_id")
        if (
            isinstance(public_id, str)
            and public_id.startswith(prefix)
            and public_id not in public_ids
        ):
            public_ids.append(public_id)
    return public_ids


def destroy_photo(public_id):
    """Best-effort deletion of a single Cloudinary asset."""
    if not is_configured():
        return False
    if (
        not isinstance(public_id, str)
        or not public_id
        or len(public_id) > MAX_PUBLIC_ID_LENGTH
    ):
        return False

    config = _config()
    timestamp = int(time.time())
    params = {"public_id": public_id, "timestamp": timestamp}

    try:
        body = urlencode(
            {
                "public_id": public_id,
                "timestamp": str(timestamp),
                "api_key": config["api_key"],
                "signature": _sign(params),
            }
        ).encode("utf-8")
        request = Request(
            "https://api.cloudinary.com/v1_1/"
            f"{config['cloud_name']}/image/destroy",
            data=body,
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
        return payload.get("result") in ("ok", "not found")
    except Exception:
        current_app.logger.error("Failed to delete a Cloudinary photo.")
        return False


def destroy_photos(public_ids):
    for public_id in public_ids:
        destroy_photo(public_id)
