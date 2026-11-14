import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()
db = SQLAlchemy()

IS_VERCEL = os.getenv("VERCEL") == "1"

app = Flask(
    __name__,
    template_folder='templates',
    instance_path="/tmp/instance" if IS_VERCEL else None,
)

if IS_VERCEL and not os.getenv("DATABASE_URL"):
    raise RuntimeError(
        "DATABASE_URL is not set. Add the Neon PostgreSQL connection string "
        "to the Vercel project environment variables."
    )

app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY is not set. Add it to .env locally or to Vercel environment variables."
    )


def _env_int(name, default, minimum):
    try:
        return max(minimum, int(os.getenv(name, default)))
    except (TypeError, ValueError):
        return max(minimum, default)


app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_VERCEL or os.getenv("SESSION_COOKIE_SECURE") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    PREFERRED_URL_SCHEME="https" if IS_VERCEL else "http",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    WTF_CSRF_TIME_LIMIT=None,
    PASSWORD_MIN_LENGTH=_env_int("PASSWORD_MIN_LENGTH", 12, 12),
    PASSWORD_MAX_LENGTH=256,
    RATELIMIT_HEADERS_ENABLED=True,
)

csrf = CSRFProtect(app)

RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "").strip()
if not RATELIMIT_STORAGE_URI:
    RATELIMIT_STORAGE_URI = "memory://"

if RATELIMIT_STORAGE_URI.startswith(("http://", "https://")):
    raise RuntimeError(
        "RATELIMIT_STORAGE_URI must be a Redis URI such as "
        "rediss://default:password@host:port, not an Upstash REST URL."
    )

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=RATELIMIT_STORAGE_URI,
)

if IS_VERCEL and RATELIMIT_STORAGE_URI == "memory://":
    app.logger.warning(
        "RATELIMIT_STORAGE_URI is not set to a shared Redis instance. "
        "Rate limits will be stored per instance and will not be shared "
        "across Vercel serverless instances."
    )

AUTH_ENDPOINTS = {"login", "signup", "forgot_password", "reset_password"}


@app.after_request
def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Referrer-Policy",
        "strict-origin-when-cross-origin",
    )
    response.headers.setdefault(
        "Permissions-Policy",
        "microphone=(self), camera=(), geolocation=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: blob: https://res.cloudinary.com; "
        "media-src 'self' blob: https://res.cloudinary.com; "
        "script-src 'self'; style-src 'self'; "
        "connect-src 'self' https://api.cloudinary.com; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if IS_VERCEL:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    if response.mimetype == "text/html":
        response.headers.setdefault("Cache-Control", "no-store")
    if request.endpoint in AUTH_ENDPOINTS:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    return (
        render_template(
            "error.html",
            code=400,
            message="Your form session expired or the request was invalid. Please try again.",
        ),
        400,
    )


@app.errorhandler(413)
def handle_request_too_large(error):
    return (
        render_template(
            "error.html",
            code=413,
            message="The request is too large.",
        ),
        413,
    )


@app.errorhandler(404)
def handle_not_found(error):
    return (
        render_template(
            "error.html",
            code=404,
            message="The page or memory could not be found.",
        ),
        404,
    )


@app.errorhandler(500)
def handle_server_error(error):
    app.logger.error("Unhandled application error: %s", error)
    return (
        render_template(
            "error.html",
            code=500,
            message="Something went wrong. Please try again.",
        ),
        500,
    )


database_url = os.getenv("DATABASE_URL", "").strip() or "sqlite:///memoryvault.db"

if database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
    database_url = "postgresql+psycopg2://" + database_url.split("://", 1)[1]

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300}

db.init_app(app)


class User(db.Model):
    __tablename__ = 'users'

    uid = db.Column(db.Integer,primary_key=True)
    username = db.Column(db.String,nullable=False,unique=True)
    password = db.Column(db.String,nullable=False)

    def __repr__(self):
        return f'<User: {self.username}>'

class Memory(db.Model):
    __tablename__ = 'memories'

    mid = db.Column(db.Integer,primary_key=True)
    title = db.Column(db.String,nullable=False)
    message = db.Column(db.String,nullable=False)
    open_date=db.Column(db.Date,nullable=False)
    created_on = db.Column(db.Date,nullable=False)
    user_id= db.Column(db.Integer,db.ForeignKey('users.uid'),nullable=False)

    def __repr__(self):
        return f'<Memory: {self.title}>'


with app.app_context():
    db.create_all()

from routes import *

if __name__ == '__main__':
    app.run(debug=True)