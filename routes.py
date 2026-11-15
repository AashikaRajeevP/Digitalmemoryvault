import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from app import EmailVerification, Memory, User, app, db, limiter
from services.accounts import is_valid_email, normalize_email
from services.email import send_otp_email
from services.otp import generate_otp, hash_otp, verify_otp
from services.security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    is_password_hash,
    verify_password,
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _purge_expired_verifications():
    now = _utcnow()
    EmailVerification.query.filter(
        (EmailVerification.used.is_(True)) | (EmailVerification.expires_at <= now)
    ).delete(synchronize_session=False)
    db.session.commit()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None or db.session.get(User, user_id) is None:
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

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    email = normalize_email(request.form.get('email', ''))
    min_length = app.config['PASSWORD_MIN_LENGTH']
    max_length = app.config['PASSWORD_MAX_LENGTH']

    if not 3 <= len(username) <= 80:
        flash("Username must be between 3 and 80 characters.", "error")
        return render_template('signup.html'), 400

    if len(password) < min_length:
        flash(f"Password must be at least {min_length} characters.", "error")
        return render_template('signup.html'), 400

    if len(password) > max_length:
        flash(f"Password must be at most {max_length} characters.", "error")
        return render_template('signup.html'), 400

    if not email or not is_valid_email(email):
        flash("Please enter a valid email address.", "error")
        return render_template('signup.html'), 400

    _purge_expired_verifications()

    if User.query.filter(
        (User.username == username) | (User.email == email)
    ).first() is not None:
        flash("That username or email is already in use.", "error")
        return render_template('signup.html'), 400

    EmailVerification.query.filter_by(email=email, used=False).update(
        {"used": True}, synchronize_session=False
    )

    if EmailVerification.query.filter_by(username=username, used=False).first() is not None:
        db.session.rollback()
        flash("That username is already in use.", "error")
        return render_template('signup.html'), 400

    token = secrets.token_urlsafe(32)
    otp = generate_otp()
    now = _utcnow()

    challenge = EmailVerification(
        token=token,
        username=username,
        email=email,
        password_hash=hash_password(password),
        otp_hash=hash_otp(app.config['OTP_SECRET'], token, otp),
        attempts=0,
        used=False,
        expires_at=now + timedelta(seconds=app.config['OTP_TTL_SECONDS']),
        last_sent_at=now,
        created_at=now,
    )

    db.session.add(challenge)
    db.session.commit()

    if not send_otp_email(email, otp):
        challenge.used = True
        db.session.commit()
        flash("We could not send the verification email. Please try again.", "error")
        return render_template('signup.html'), 502

    session['pending_signup_token'] = token
    flash("Enter the 6-digit code we emailed you.", "success")
    return redirect(url_for('signup_verify'))


@app.route('/signup/verify', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def signup_verify():
    token = session.get('pending_signup_token')

    if not token:
        flash("Please start signup again.", "error")
        return redirect(url_for('signup'))

    challenge = EmailVerification.query.filter_by(token=token).first()
    now = _utcnow()

    if challenge is None:
        session.pop('pending_signup_token', None)
        flash("Please start signup again.", "error")
        return redirect(url_for('signup'))

    if challenge.used or challenge.expires_at <= now:
        session.pop('pending_signup_token', None)
        flash("That verification code has expired. Please sign up again.", "error")
        return redirect(url_for('signup'))

    if request.method == 'GET':
        return render_template('verify.html', email=challenge.email)

    otp = request.form.get('otp', '').strip()

    if challenge.attempts >= app.config['OTP_MAX_ATTEMPTS']:
        challenge.used = True
        db.session.commit()
        session.pop('pending_signup_token', None)
        flash("Too many incorrect attempts. Please sign up again.", "error")
        return redirect(url_for('signup'))

    if not (otp.isdigit() and len(otp) == 6) or not verify_otp(
        app.config['OTP_SECRET'], token, otp, challenge.otp_hash
    ):
        challenge.attempts += 1
        if challenge.attempts >= app.config['OTP_MAX_ATTEMPTS']:
            challenge.used = True
            db.session.commit()
            session.pop('pending_signup_token', None)
            flash("Too many incorrect attempts. Please sign up again.", "error")
            return redirect(url_for('signup'))
        db.session.commit()
        flash("That code is incorrect.", "error")
        return render_template('verify.html', email=challenge.email), 400

    challenge.used = True

    if User.query.filter(
        (User.username == challenge.username) | (User.email == challenge.email)
    ).first() is not None:
        db.session.commit()
        session.pop('pending_signup_token', None)
        flash("That username or email is already in use.", "error")
        return redirect(url_for('login'))

    user = User(
        username=challenge.username,
        email=challenge.email,
        password=challenge.password_hash,
        email_verified=True,
    )

    db.session.add(user)
    db.session.commit()

    session.pop('pending_signup_token', None)
    flash("Account verified. Please log in.", "success")
    return redirect(url_for('login'))


@app.route('/signup/resend', methods=['POST'])
@limiter.limit("5 per hour")
def signup_resend():
    token = session.get('pending_signup_token')
    challenge = (
        EmailVerification.query.filter_by(token=token).first() if token else None
    )

    if challenge is None or challenge.used:
        session.pop('pending_signup_token', None)
        flash("Please start signup again.", "error")
        return redirect(url_for('signup'))

    now = _utcnow()

    if challenge.expires_at <= now:
        challenge.used = True
        db.session.commit()
        session.pop('pending_signup_token', None)
        flash("That verification code has expired. Please sign up again.", "error")
        return redirect(url_for('signup'))

    cooldown = app.config['OTP_RESEND_COOLDOWN_SECONDS']

    if (now - challenge.last_sent_at).total_seconds() < cooldown:
        flash("Please wait before requesting another code.", "error")
        return redirect(url_for('signup_verify'))

    otp = generate_otp()
    challenge.otp_hash = hash_otp(app.config['OTP_SECRET'], token, otp)
    challenge.attempts = 0
    challenge.expires_at = now + timedelta(seconds=app.config['OTP_TTL_SECONDS'])
    challenge.last_sent_at = now
    db.session.commit()

    if not send_otp_email(challenge.email, otp):
        challenge.used = True
        db.session.commit()
        flash("We could not send the verification email. Please try again.", "error")
        return redirect(url_for('signup_verify'))

    flash("A new code has been sent.", "success")
    return redirect(url_for('signup_verify'))


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

    if not user.email_verified:
        flash("Invalid email or password.", "error")
        return render_template('login.html'), 401

    if not is_password_hash(user.password):
        user.password = hash_password(password)
        db.session.commit()

    session.clear()
    session['user_id'] = user.uid
    session.permanent = True
    flash("Welcome back.", "success")
    return redirect(url_for('index'))


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))


@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    user = db.session.get(User, session['user_id'])

    if request.method == 'GET':
        return render_template('account.html', user=user)

    email = normalize_email(request.form.get('email', ''))

    if not email or not is_valid_email(email):
        flash("Please enter a valid email address.", "error")
        return render_template('account.html', user=user), 400

    existing = User.query.filter(
        User.email == email,
        User.uid != user.uid,
    ).first()

    if existing is not None:
        flash("That email address is already in use.", "error")
        return render_template('account.html', user=user), 400

    user.email = email

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("That email address is already in use.", "error")
        return render_template('account.html', user=user), 400

    flash("Email updated.", "success")
    return redirect(url_for('account'))


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
