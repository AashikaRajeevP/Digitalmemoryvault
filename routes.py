import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from app import Memory, PasswordReset, User, app, db, limiter
from services.accounts import is_valid_email, normalize_email
from services.email import send_otp_email
from services.otp import generate_otp, hash_otp, hash_token, verify_otp
from services.security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    is_password_hash,
    verify_password,
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _purge_expired_resets():
    now = _utcnow()
    PasswordReset.query.filter(
        (PasswordReset.used.is_(True)) | (PasswordReset.expires_at <= now)
    ).delete(synchronize_session=False)
    db.session.commit()


INTERNAL_USERNAME_PREFIX = "user:"
MAX_USERNAME_GENERATION_ATTEMPTS = 5


def _generate_internal_username(email):
    """Return an internal username that is not already used by an account.

    The legacy users.username column is still NOT NULL UNIQUE, but username is
    no longer collected at signup or used for login. New accounts get a
    generated value based on the normalized email. If an old account already
    owns that value, add a numeric suffix until a free value is found.
    """
    base = f"{INTERNAL_USERNAME_PREFIX}{email}"
    candidate = base
    suffix = 2

    while User.query.filter_by(username=candidate).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1

    return candidate


def _create_user(email, password_hash):
    """Create a new user immediately, retrying internal username collisions.

    Returns (user, error). error is None on success, "email_taken" when the
    email was registered in the meantime, or "failed" after repeated database
    conflicts.
    """
    for _ in range(MAX_USERNAME_GENERATION_ATTEMPTS):
        if User.query.filter_by(email=email).first() is not None:
            return None, "email_taken"

        user = User(
            username=_generate_internal_username(email),
            email=email,
            password=password_hash,
            email_verified=False,
        )
        db.session.add(user)

        try:
            db.session.commit()
            return user, None
        except IntegrityError:
            db.session.rollback()

    return None, "failed"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        user = db.session.get(User, user_id) if user_id is not None else None
        if user is None or session.get("auth_version") != (user.auth_version or 1):
            session.clear()
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.route('/')
def index():
    total = 0
    locked = 0
    unlocked = 0

    if 'user_id' in session:
        memories = Memory.query.filter_by(user_id=session['user_id']).all()

        total = len(memories)

        for memory in memories:
            if memory.open_date > date.today():
                locked += 1
            else:
                unlocked += 1

    return render_template('index.html', total=total, locked=locked, unlocked=unlocked)


@app.route('/signup', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def signup():
    if request.method == 'GET':
        return render_template('signup.html')

    password = request.form.get('password', '')
    email = normalize_email(request.form.get('email', ''))
    min_length = app.config['PASSWORD_MIN_LENGTH']
    max_length = app.config['PASSWORD_MAX_LENGTH']

    if len(password) < min_length:
        flash(f"Password must be at least {min_length} characters.", "error")
        return render_template('signup.html'), 400

    if len(password) > max_length:
        flash(f"Password must be at most {max_length} characters.", "error")
        return render_template('signup.html'), 400

    if not email or not is_valid_email(email):
        flash("Please enter a valid email address.", "error")
        return render_template('signup.html'), 400

    if User.query.filter_by(email=email).first() is not None:
        flash("That email address is already in use.", "error")
        return render_template('signup.html'), 400

    _user, error = _create_user(email, hash_password(password))

    if error == "email_taken":
        flash("That email address is already in use.", "error")
        return render_template('signup.html'), 400

    if error is not None:
        flash("We could not create your account. Please try again.", "error")
        return render_template('signup.html'), 500

    flash("Account created. Please log in.", "success")
    return redirect(url_for('login'))


RESET_SESSION_KEY = 'pending_reset_token'


def _pending_reset():
    token = session.get(RESET_SESSION_KEY)
    if not token:
        return None, None
    challenge = PasswordReset.query.filter_by(
        token_hash=hash_token(app.config['OTP_SECRET'], token),
        used=False,
    ).first()
    return token, challenge


@app.route('/forgot_password', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def forgot_password():
    if request.method == 'GET':
        return render_template('forgot_password.html')

    email = normalize_email(request.form.get('email', ''))

    if not email or not is_valid_email(email):
        flash("Please enter a valid email address.", "error")
        return render_template('forgot_password.html'), 400

    _purge_expired_resets()

    user = User.query.filter_by(email=email).first()

    PasswordReset.query.filter_by(email=email, used=False).update(
        {"used": True}, synchronize_session=False
    )

    token = secrets.token_urlsafe(32)
    otp = generate_otp()
    now = _utcnow()

    challenge = PasswordReset(
        user_id=user.uid if user is not None else None,
        email=email,
        token_hash=hash_token(app.config['OTP_SECRET'], token),
        otp_hash=hash_otp(app.config['OTP_SECRET'], token, otp),
        attempts=0,
        used=False,
        expires_at=now + timedelta(seconds=app.config['OTP_TTL_SECONDS']),
        last_sent_at=now,
        created_at=now,
    )

    db.session.add(challenge)
    db.session.commit()

    session[RESET_SESSION_KEY] = token

    if user is not None and not send_otp_email(email, otp):
        challenge.used = True
        db.session.commit()

    flash(
        "If an account exists for that email, we've sent a password reset code.",
        "success",
    )
    return redirect(url_for('reset_password'))


@app.route('/reset_password', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def reset_password():
    token, challenge = _pending_reset()
    now = _utcnow()

    if challenge is None or challenge.expires_at <= now:
        session.pop(RESET_SESSION_KEY, None)
        if request.method == 'GET':
            flash("Please request a password reset code.", "error")
            return redirect(url_for('forgot_password'))
        flash("That code is invalid or has expired.", "error")
        return redirect(url_for('forgot_password'))

    if request.method == 'GET':
        return render_template('reset_password.html', email=challenge.email)

    if challenge.attempts >= app.config['OTP_MAX_ATTEMPTS']:
        challenge.used = True
        db.session.commit()
        session.pop(RESET_SESSION_KEY, None)
        flash("That code is invalid or has expired.", "error")
        return redirect(url_for('forgot_password'))

    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    min_length = app.config['PASSWORD_MIN_LENGTH']
    max_length = app.config['PASSWORD_MAX_LENGTH']

    if len(password) < min_length or len(password) > max_length:
        flash(
            f"Password must be between {min_length} and {max_length} characters.",
            "error",
        )
        return render_template('reset_password.html', email=challenge.email), 400

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template('reset_password.html', email=challenge.email), 400

    otp = request.form.get('otp', '').strip()

    if not (otp.isdigit() and len(otp) == 6) or not verify_otp(
        app.config['OTP_SECRET'], token, otp, challenge.otp_hash
    ):
        challenge.attempts += 1

        if challenge.attempts >= app.config['OTP_MAX_ATTEMPTS']:
            challenge.used = True
            db.session.commit()
            session.pop(RESET_SESSION_KEY, None)
            flash("That code is invalid or has expired.", "error")
            return redirect(url_for('forgot_password'))

        db.session.commit()
        flash("That code is invalid or has expired.", "error")
        return render_template('reset_password.html', email=challenge.email), 400

    user = db.session.get(User, challenge.user_id) if challenge.user_id else None

    if user is None or user.email != challenge.email:
        challenge.used = True
        db.session.commit()
        session.pop(RESET_SESSION_KEY, None)
        flash("That code is invalid or has expired.", "error")
        return redirect(url_for('forgot_password'))

    consumed = PasswordReset.query.filter_by(
        id=challenge.id, used=False
    ).update({"used": True}, synchronize_session=False)

    if not consumed:
        db.session.rollback()
        flash("That code is invalid or has expired.", "error")
        return redirect(url_for('forgot_password'))

    user.password = hash_password(password)
    user.auth_version = (user.auth_version or 1) + 1
    db.session.commit()

    session.clear()
    flash("Your password has been reset. Please log in.", "success")
    return redirect(url_for('login'))


@app.route('/reset_password/resend', methods=['POST'])
@limiter.limit("5 per hour")
def reset_resend():
    token, challenge = _pending_reset()

    if challenge is None:
        session.pop(RESET_SESSION_KEY, None)
        flash("Please request a password reset code.", "error")
        return redirect(url_for('forgot_password'))

    now = _utcnow()

    if challenge.expires_at <= now:
        challenge.used = True
        db.session.commit()
        session.pop(RESET_SESSION_KEY, None)
        flash("Please request a password reset code.", "error")
        return redirect(url_for('forgot_password'))

    cooldown = app.config['OTP_RESEND_COOLDOWN_SECONDS']

    if (now - challenge.last_sent_at).total_seconds() < cooldown:
        flash("Please wait before requesting another code.", "error")
        return redirect(url_for('reset_password'))

    otp = generate_otp()
    challenge.otp_hash = hash_otp(app.config['OTP_SECRET'], token, otp)
    challenge.attempts = 0
    challenge.expires_at = now + timedelta(seconds=app.config['OTP_TTL_SECONDS'])
    challenge.last_sent_at = now
    db.session.commit()

    user = db.session.get(User, challenge.user_id) if challenge.user_id else None

    if user is not None and user.email == challenge.email:
        if not send_otp_email(challenge.email, otp):
            challenge.used = True
            db.session.commit()

    flash("If a reset request is active, a new code has been sent.", "success")
    return redirect(url_for('reset_password'))


@app.route('/login', methods=['POST', 'GET'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'GET':
        return render_template('login.html')

    email = normalize_email(request.form.get('email', ''))
    password = request.form.get('password', '')
    user = User.query.filter_by(email=email).first() if email else None

    if user is None:
        verify_password(DUMMY_PASSWORD_HASH, password)
        flash("Invalid email or password.", "error")
        return render_template('login.html'), 401

    if not verify_password(user.password, password):
        flash("Invalid email or password.", "error")
        return render_template('login.html'), 401

    if not is_password_hash(user.password):
        user.password = hash_password(password)
        db.session.commit()

    session.clear()
    session['user_id'] = user.uid
    session['auth_version'] = user.auth_version or 1
    session.permanent = True
    flash("Welcome back.", "success")
    return redirect(url_for('index'))


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))


@app.route('/create_memory', methods=['GET', 'POST'])
@login_required
@limiter.limit("60 per hour")
def create_memory():
    if request.method == 'GET':
        return render_template('create_memory.html')

    title = request.form.get('title', '').strip()
    message = request.form.get('message', '').strip()
    open_date_raw = request.form.get('open_date', '').strip()

    if not title or len(title) > 200:
        flash("Title is required and must be at most 200 characters.", "error")
        return render_template('create_memory.html'), 400

    if not message or len(message) > 20000:
        flash("Memory text is required and must be at most 20000 characters.", "error")
        return render_template('create_memory.html'), 400

    try:
        open_date = date.fromisoformat(open_date_raw)
    except ValueError:
        flash("Please choose a valid open date.", "error")
        return render_template('create_memory.html'), 400

    memory = Memory(
        title=title,
        message=message,
        open_date=open_date,
        created_on=date.today(),
        user_id=session['user_id'],
    )

    db.session.add(memory)
    db.session.commit()

    flash("Memory created.", "success")
    return redirect(url_for('my_memories'))


@app.route('/my_memories')
@login_required
def my_memories():
    memories = Memory.query.filter_by(user_id=session['user_id']).all()

    return render_template("my_memories.html", memories=memories, today=date.today())


@app.route('/memory_detail/<int:mid>')
@login_required
def memory_detail(mid):
    memory = Memory.query.filter_by(
        mid=mid,
        user_id=session['user_id'],
    ).first_or_404()

    return render_template('memory_detail.html', memory=memory, today=date.today())
