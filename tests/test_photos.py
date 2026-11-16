import hashlib
import json
import re
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import SQLAlchemyError

from services import photos as photo_service
from services.security import hash_password

CLOUD_NAME = "test-cloud"


def create_user(
    app_module,
    username="alice",
    email=None,
    password="password1234",
):
    with app_module.app.app_context():
        user = app_module.User(
            username=username,
            password=hash_password(password),
            email=email or f"{username}@example.com",
            email_verified=True,
        )
        app_module.db.session.add(user)
        app_module.db.session.commit()
        return user.uid


def login(client, email="alice@example.com", password="password1234"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
    )


def make_memory(app_module, user_id, title="A memory", open_date=None):
    with app_module.app.app_context():
        memory = app_module.Memory(
            title=title,
            message="A private memory message.",
            open_date=open_date or date.today(),
            created_on=date.today(),
            user_id=user_id,
        )
        app_module.db.session.add(memory)
        app_module.db.session.commit()
        return memory.mid


def add_photo(
    app_module,
    memory_id,
    public_id,
    secure_url,
    is_cover=False,
    position=0,
):
    with app_module.app.app_context():
        photo = app_module.MemoryPhoto(
            memory_id=memory_id,
            public_id=public_id,
            secure_url=secure_url,
            is_cover=is_cover,
            position=position,
            width=800,
            height=600,
            image_format="jpg",
            bytes=1024,
        )
        app_module.db.session.add(photo)
        app_module.db.session.commit()
        return photo.id


def photo_payload(
    user_id=1,
    index=1,
    is_cover=False,
    fmt="jpg",
    size=1024,
    public_id=None,
    secure_url=None,
    width=800,
    height=600,
):
    resolved_public_id = public_id or f"memoryvault/users/{user_id}/photo-{index}"
    resolved_url = secure_url or (
        "https://res.cloudinary.com/"
        f"{CLOUD_NAME}/image/upload/v1700000000/"
        f"{resolved_public_id}.{fmt}"
    )
    return {
        "public_id": resolved_public_id,
        "secure_url": resolved_url,
        "is_cover": is_cover,
        "format": fmt,
        "bytes": size,
        "width": width,
        "height": height,
    }


def post_memory(client, photos, title="A memory", open_date="2030-01-01"):
    return client.post(
        "/create_memory",
        data={
            "title": title,
            "message": "A private memory message.",
            "open_date": open_date,
            "photos": json.dumps(photos) if photos else "",
        },
    )


def meta_csrf(response):
    match = re.search(
        r'<meta name="csrf-token" content="([^"]+)"',
        response.get_data(as_text=True),
    )
    assert match is not None
    return match.group(1)


@pytest.fixture
def cloudinary(app):
    app.config.update(
        CLOUDINARY_CLOUD_NAME=CLOUD_NAME,
        CLOUDINARY_API_KEY="test-key",
        CLOUDINARY_API_SECRET="test-secret",
        CLOUDINARY_UPLOAD_FOLDER="memoryvault",
        MAX_PHOTOS_PER_MEMORY=10,
        MAX_PHOTO_BYTES=10 * 1024 * 1024,
    )
    return app


@pytest.fixture
def deleted_assets(monkeypatch):
    deleted = []

    def fake_destroy(public_id):
        deleted.append(public_id)
        return True

    monkeypatch.setattr(photo_service, "destroy_photo", fake_destroy)
    return deleted


def test_signature_requires_login(client):
    response = client.post("/photos/signature")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_signature_returns_503_when_unconfigured(client, app_module):
    create_user(app_module)
    login(client)

    response = client.post("/photos/signature")

    assert response.status_code == 503
    assert "not configured" in response.get_json()["error"]


def test_signature_returns_signed_params_without_secret(
    client, app_module, cloudinary
):
    uid = create_user(app_module)
    login(client)

    response = client.post("/photos/signature")

    assert response.status_code == 200
    assert b"test-secret" not in response.data

    data = response.get_json()
    assert data["cloud_name"] == CLOUD_NAME
    assert data["api_key"] == "test-key"
    assert data["folder"] == f"memoryvault/users/{uid}"
    assert data["allowed_formats"] == "jpg,jpeg,png,webp,gif"
    assert "max_file_size" not in data
    assert data["upload_url"].endswith(f"/{CLOUD_NAME}/image/upload")

    params = {
        "folder": data["folder"],
        "timestamp": data["timestamp"],
        "allowed_formats": data["allowed_formats"],
    }
    to_sign = "&".join(f"{key}={params[key]}" for key in sorted(params))
    expected = hashlib.sha1((to_sign + "test-secret").encode("utf-8")).hexdigest()
    assert data["signature"] == expected


def test_signature_requires_csrf(client, app, app_module, cloudinary):
    create_user(app_module)
    login(client)

    app.config["WTF_CSRF_ENABLED"] = True
    token = meta_csrf(client.get("/create_memory"))

    assert client.post("/photos/signature").status_code == 400

    response = client.post(
        "/photos/signature",
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 200


def test_create_memory_with_photos_and_cover(
    client, app_module, cloudinary
):
    uid = create_user(app_module)
    login(client)

    photos = [
        photo_payload(uid, index=1, is_cover=True),
        photo_payload(uid, index=2),
    ]

    response = post_memory(client, photos)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/my_memories")

    with app_module.app.app_context():
        memory = app_module.Memory.query.one()
        assert len(memory.photos) == 2
        assert memory.cover_photo.public_id == photos[0]["public_id"]
        assert memory.photos[0].position == 0
        assert memory.photos[1].position == 1
        assert memory.photos[0].secure_url == photos[0]["secure_url"]
        assert memory.photos[0].image_format == "jpg"
        assert memory.photos[0].bytes == 1024
        assert memory.photos[0].width == 800
        assert memory.photos[1].is_cover is False


def test_create_memory_without_photos_still_works(
    client, app_module, cloudinary
):
    uid = create_user(app_module)
    login(client)

    response = post_memory(client, [])

    assert response.status_code == 302

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 1
        assert app_module.MemoryPhoto.query.count() == 0


def test_first_photo_becomes_cover_when_none_selected(
    client, app_module, cloudinary
):
    uid = create_user(app_module)
    login(client)

    response = post_memory(
        client,
        [photo_payload(uid, index=1), photo_payload(uid, index=2)],
    )

    assert response.status_code == 302

    with app_module.app.app_context():
        memory = app_module.Memory.query.one()
        assert memory.photos[0].is_cover is True
        assert memory.photos[1].is_cover is False


def test_maximum_photo_limit_is_enforced(
    client, app_module, cloudinary, deleted_assets
):
    uid = create_user(app_module)
    login(client)
    cloudinary.config["MAX_PHOTOS_PER_MEMORY"] = 2

    photos = [photo_payload(uid, index=index) for index in (1, 2, 3)]

    response = post_memory(client, photos)

    assert response.status_code == 400
    assert b"up to 2 photos" in response.data

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0
        assert app_module.MemoryPhoto.query.count() == 0

    assert sorted(deleted_assets) == sorted(
        photo["public_id"] for photo in photos
    )


def test_unsupported_photo_type_is_rejected(
    client, app_module, cloudinary, deleted_assets
):
    uid = create_user(app_module)
    login(client)

    photo = photo_payload(uid, index=1, fmt="pdf")

    response = post_memory(client, [photo])

    assert response.status_code == 400
    assert b"Unsupported photo type" in response.data

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0

    assert deleted_assets == [photo["public_id"]]


def test_oversized_photo_is_rejected(
    client, app_module, cloudinary, deleted_assets
):
    uid = create_user(app_module)
    login(client)
    cloudinary.config["MAX_PHOTO_BYTES"] = 1000

    photo = photo_payload(uid, index=1, size=2000)

    response = post_memory(client, [photo])

    assert response.status_code == 400
    assert b"too large" in response.data

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0

    assert deleted_assets == [photo["public_id"]]


def test_non_cloudinary_url_is_rejected(
    client, app_module, cloudinary, deleted_assets
):
    uid = create_user(app_module)
    login(client)

    photo = photo_payload(
        uid,
        index=1,
        secure_url=f"https://evil.example.com/{uid}/photo.jpg",
    )

    response = post_memory(client, [photo])

    assert response.status_code == 400
    assert b"could not be verified" in response.data

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0

    assert deleted_assets == [photo["public_id"]]


def test_photo_from_another_user_folder_is_rejected_and_not_deleted(
    client, app_module, cloudinary, deleted_assets
):
    alice_id = create_user(app_module, username="alice")
    create_user(app_module, username="bob")
    login(client, email="bob@example.com")

    photo = photo_payload(alice_id, index=1)

    response = post_memory(client, [photo])

    assert response.status_code == 400
    assert b"could not be verified" in response.data

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0

    assert deleted_assets == []


def test_duplicate_photo_in_payload_is_rejected(
    client, app_module, cloudinary, deleted_assets
):
    uid = create_user(app_module)
    login(client)

    photo = photo_payload(uid, index=1)

    response = post_memory(client, [photo, dict(photo)])

    assert response.status_code == 400
    assert b"attached more than once" in response.data

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0

    assert deleted_assets == [photo["public_id"]]


def test_photo_already_attached_is_rejected_without_deleting_it(
    client, app_module, cloudinary, deleted_assets
):
    uid = create_user(app_module)
    existing_photo = photo_payload(uid, index=1)
    existing_mid = make_memory(app_module, uid, title="Existing")
    add_photo(
        app_module,
        existing_mid,
        existing_photo["public_id"],
        existing_photo["secure_url"],
        is_cover=True,
    )
    login(client)

    response = post_memory(client, [existing_photo])

    assert response.status_code == 400
    assert b"already attached" in response.data

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 1
        assert app_module.MemoryPhoto.query.count() == 1

    assert deleted_assets == []


def test_photos_are_cleaned_up_when_saving_the_memory_fails(
    client, app_module, cloudinary, deleted_assets, monkeypatch
):
    uid = create_user(app_module)
    login(client)

    photo = photo_payload(uid, index=1)

    def failing_commit():
        raise SQLAlchemyError("simulated commit failure")

    monkeypatch.setattr(app_module.db.session, "commit", failing_commit)

    response = post_memory(client, [photo])

    assert response.status_code == 500

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0
        assert app_module.MemoryPhoto.query.count() == 0

    assert deleted_assets == [photo["public_id"]]


def test_locked_memory_detail_shows_cover_but_not_additional_photos(
    client, app_module, cloudinary
):
    uid = create_user(app_module)
    mid = make_memory(
        app_module,
        uid,
        title="Locked memory",
        open_date=date.today() + timedelta(days=5),
    )
    cover_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/cover-visible.jpg"
    )
    hidden_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/gallery-secret.jpg"
    )
    add_photo(app_module, mid, "memoryvault/users/1/cover-visible", cover_url, True, 0)
    add_photo(
        app_module,
        mid,
        "memoryvault/users/1/gallery-secret",
        hidden_url,
        False,
        1,
    )
    login(client)

    response = client.get(f"/memory_detail/{mid}")

    assert response.status_code == 200
    assert b"Locked memory" in response.data
    assert cover_url.encode() in response.data
    assert b"gallery-secret" not in response.data
    assert b"This memory is still locked" in response.data
    assert b"Photo gallery" not in response.data


def test_unlocked_memory_detail_shows_cover_and_gallery(
    client, app_module, cloudinary
):
    uid = create_user(app_module)
    mid = make_memory(app_module, uid, title="Open memory", open_date=date.today())
    cover_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/cover.jpg"
    )
    gallery_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/gallery.jpg"
    )
    add_photo(app_module, mid, "memoryvault/users/1/cover", cover_url, True, 0)
    add_photo(app_module, mid, "memoryvault/users/1/gallery", gallery_url, False, 1)
    login(client)

    response = client.get(f"/memory_detail/{mid}")

    assert response.status_code == 200
    assert b"Open memory" in response.data
    assert cover_url.encode() in response.data
    assert gallery_url.encode() in response.data
    assert b"Photo gallery" in response.data


def test_memory_cards_show_cover_but_not_additional_photos(
    client, app_module, cloudinary
):
    uid = create_user(app_module)
    mid = make_memory(
        app_module,
        uid,
        title="Card memory",
        open_date=date.today() + timedelta(days=3),
    )
    cover_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/card-cover.jpg"
    )
    hidden_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/card-secret.jpg"
    )
    add_photo(app_module, mid, "memoryvault/users/1/card-cover", cover_url, True, 0)
    add_photo(
        app_module,
        mid,
        "memoryvault/users/1/card-secret",
        hidden_url,
        False,
        1,
    )
    login(client)

    response = client.get("/my_memories")

    assert response.status_code == 200
    assert b"Card memory" in response.data
    assert cover_url.encode() in response.data
    assert b"card-secret" not in response.data


def test_another_user_cannot_view_memory_or_photos(
    client, app_module, cloudinary
):
    alice_id = create_user(app_module, username="alice")
    create_user(app_module, username="bob")
    mid = make_memory(app_module, alice_id, title="Alice only", open_date=date.today())
    cover_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/alice-cover.jpg"
    )
    add_photo(
        app_module,
        mid,
        "memoryvault/users/1/alice-cover",
        cover_url,
        is_cover=True,
    )
    login(client, email="bob@example.com")

    response = client.get(f"/memory_detail/{mid}")

    assert response.status_code == 404
    assert b"alice-cover" not in response.data


def test_delete_memory_removes_photos_and_cloudinary_assets(
    client, app_module, cloudinary, deleted_assets
):
    uid = create_user(app_module)
    mid = make_memory(app_module, uid, title="Delete me")
    add_photo(
        app_module,
        mid,
        "memoryvault/users/1/cover",
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/cover.jpg",
        True,
        0,
    )
    add_photo(
        app_module,
        mid,
        "memoryvault/users/1/extra",
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/extra.jpg",
        False,
        1,
    )
    login(client)

    response = client.post(f"/memory_detail/{mid}/delete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/my_memories")

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 0
        assert app_module.MemoryPhoto.query.count() == 0

    assert sorted(deleted_assets) == [
        "memoryvault/users/1/cover",
        "memoryvault/users/1/extra",
    ]


def test_another_user_cannot_delete_a_memory(
    client, app_module, cloudinary, deleted_assets
):
    alice_id = create_user(app_module, username="alice")
    create_user(app_module, username="bob")
    mid = make_memory(app_module, alice_id, title="Alice only")
    add_photo(
        app_module,
        mid,
        "memoryvault/users/1/alice-cover",
        "https://res.cloudinary.com/test-cloud/image/upload/v1/"
        "memoryvault/users/1/alice-cover.jpg",
        True,
        0,
    )
    login(client, email="bob@example.com")

    response = client.post(f"/memory_detail/{mid}/delete")

    assert response.status_code == 404

    with app_module.app.app_context():
        assert app_module.Memory.query.count() == 1
        assert app_module.MemoryPhoto.query.count() == 1

    assert deleted_assets == []


def test_delete_memory_requires_csrf(client, app, app_module, cloudinary):
    uid = create_user(app_module)
    mid = make_memory(app_module, uid)
    login(client)

    app.config["WTF_CSRF_ENABLED"] = True
    token = meta_csrf(client.get(f"/memory_detail/{mid}"))

    assert client.post(f"/memory_detail/{mid}/delete").status_code == 400

    response = client.post(
        f"/memory_detail/{mid}/delete",
        data={"csrf_token": token},
    )
    assert response.status_code == 302
