"""
LockIn Authentication Routes
CM2211 Group 07 — Internet of Things

Handles user login/logout via session cookies (flask-login).
"""

import logging
import secrets
from typing import Tuple, Union
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError

from extensions import db, limiter
from validators import LoginSchema, validate_json_request

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10/minute")
def login_page() -> Union[str, Tuple[str, int]]:
    """
    Login page and form handler.

    GET: Render login form (redirect to dashboard if already authenticated)
    POST: Authenticate user via username + password
    """
    from models import User

    if current_user.is_authenticated:
        logger.debug(f"Authenticated user {current_user.id} redirected from login")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Validate input
        schema = LoginSchema()
        validated, errors = validate_json_request(
            schema,
            {'username': username, 'password': password}
        )

        if errors:
            logger.warning(f"Login validation failed: {errors}")
            for field, msgs in errors.items():
                flash(f"{field}: {msgs[0]}", 'error')
            return render_template('login.html'), 200

        try:
            user = db.session.query(User).filter_by(username=validated['username']).first()

            if user is None or not user.check_password(validated['password']):
                logger.warning(f"Failed login attempt for user: {validated['username']}")
                flash('Invalid username or password', 'error')
                return render_template('login.html'), 200

            login_user(user)
            logger.info(f"User {user.id} ({user.username}) logged in")
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.error(f"Error during login: {str(e)}", exc_info=True)
            flash('An error occurred during login', 'error')
            return render_template('login.html'), 200

    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5/minute")
def register_page() -> Union[str, Tuple[str, int]]:
    """
    Registration page and form handler.

    GET: Render registration form (redirect to dashboard if already authenticated)
    POST: Create new user account
    """
    from models import User

    if current_user.is_authenticated:
        logger.debug(f"Authenticated user {current_user.id} redirected from register")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validate input
        if not username or len(username) < 3:
            flash('Username must be at least 3 characters', 'error')
            return render_template('register.html'), 200

        if not password or len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('register.html'), 200

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html'), 200

        try:
            # Check if username already exists using db.session.query
            existing_user = db.session.query(User).filter_by(username=username).first()
            if existing_user:
                logger.warning(f"Registration failed: username '{username}' already exists")
                flash('Username already taken. Choose a different one', 'error')
                return render_template('register.html'), 200

            # Create new user with unique API key
            new_user = User(username=username, api_key=secrets.token_hex(32))
            new_user.set_password(password)

            # Add and commit in transaction
            db.session.add(new_user)
            db.session.flush()  # Flush to validate before commit
            db.session.commit()

            login_user(new_user)
            logger.info(f"New user registered and logged in: {username}")
            return redirect(url_for('auth.survey_page'))
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"IntegrityError during registration for username: {username}: {str(e)}")
            flash('Username already in use. Please choose another.', 'error')
            return render_template('register.html'), 200
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.error(f"Registration error for {username}: {str(e)}", exc_info=True)
            flash('Registration failed. Please try again.', 'error')
            return render_template('register.html'), 200

    return render_template('register.html')


@auth_bp.route('/survey', methods=['GET', 'POST'])
@login_required
def survey_page() -> Union[str, Tuple[str, int]]:
    """
    Post-registration survey.

    GET:  Render survey form (skip to dashboard if already completed)
    POST: Save profile data and redirect to dashboard
    """
    from models import UserProfile, UserSettings

    # Skip survey if already completed
    existing = db.session.query(UserProfile).filter_by(user_id=current_user.id).first()
    if existing:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        occupation = request.form.get('occupation_type', 'other')

        try:
            age_raw = request.form.get('age', '').strip()
            age = int(age_raw) if age_raw.isdigit() else None

            hours_raw = request.form.get('daily_study_hours', '').strip()
            try:
                daily_hours = float(hours_raw) if hours_raw else None
            except ValueError:
                daily_hours = None

            year_raw = request.form.get('year_of_study', '').strip()
            try:
                year = int(year_raw) if year_raw else None
            except ValueError:
                year = None

            profile = UserProfile(
                user_id=current_user.id,
                age=age,
                occupation_type=occupation,
                institution=request.form.get('institution', '').strip() or None,
                year_of_study=year,
                field_of_study=request.form.get('field_of_study', '').strip() or None,
                job_title=request.form.get('job_title', '').strip() or None,
                daily_study_hours=daily_hours,
                study_goals=request.form.get('study_goals', '').strip() or None,
            )
            db.session.add(profile)

            # Create default settings row for the device
            if not db.session.query(UserSettings).filter_by(user_id=current_user.id).first():
                db.session.add(UserSettings(user_id=current_user.id))

            db.session.commit()
            logger.info(f"Survey completed for user {current_user.id}")
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Survey save error for user {current_user.id}: {e}", exc_info=True)
            flash('Something went wrong saving your profile. You can update it later in Settings.', 'error')
            return redirect(url_for('dashboard'))

    return render_template('survey.html', username=current_user.username)


@auth_bp.route('/logout', methods=['POST'])
def logout() -> Tuple[str, int]:
    """
    Logout user and clear session cookie.

    Returns:
        redirect: 302 to login page
    """
    if current_user.is_authenticated:
        user_id = current_user.id
        logout_user()
        logger.info(f"User {user_id} logged out")
    return redirect(url_for('auth.login_page'))
