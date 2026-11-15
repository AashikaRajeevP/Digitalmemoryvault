import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DIR = Path(tempfile.mkdtemp(prefix="dmv-tests-"))
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DIR.joinpath('test.db').as_posix()}"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"
os.environ.pop("VERCEL", None)


@pytest.fixture(scope="session")
def app_module():
    import app as app_module

    return app_module


@pytest.fixture
def app(app_module):
    app_module.app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
    )
    app_module.limiter.enabled = False

    with app_module.app.app_context():
        app_module.db.drop_all()
        app_module.db.create_all()

    yield app_module.app

    with app_module.app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sent_emails(monkeypatch):
    import routes

    captured = []

    def fake_send(to_email, otp):
        captured.append((to_email, otp))
        return True

    monkeypatch.setattr(routes, "send_otp_email", fake_send)
    return captured


@pytest.fixture
def failing_email(monkeypatch):
    import routes

    def fake_send(to_email, otp):
        return False

    monkeypatch.setattr(routes, "send_otp_email", fake_send)
    return fake_send
