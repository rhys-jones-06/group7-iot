"""
LockIn Authentication Routes
CM2211 Group 07 — Internet of Things

Handles user login/logout via session cookies (flask-login).
"""

import logging
from typing import Tuple, Union
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from sqlalchemy.exc import IntegrityError

from app import db, limiter
from models import User
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
            user = User.query.filter_by(username=validated['username']).first()

            if user is None or not user.check_password(validated['password']):
                logger.warning(f"Failed login attempt for user: {validated['username']}")
                flash('Invalid username or password', 'error')
                return render_template('login.html'), 200

            login_user(user)
            logger.info(f"User {user.id} ({user.username}) logged in")
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.error(f"Error during login: {e}")
            flash('An error occurred during login', 'error')
            return render_template('login.html'), 200

    return render_template('login.html')


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
