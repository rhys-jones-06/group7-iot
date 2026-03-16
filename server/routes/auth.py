"""
LockIn Authentication Routes
CM2211 Group 07 — Internet of Things

Handles user login/logout via session cookies (flask-login).
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from app import db
from models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    """
    Login page and form handler.

    GET: Render login form (redirect to dashboard if already authenticated)
    POST: Authenticate user via username + password
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password required', 'error')
            return render_template('login.html'), 200

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Invalid username or password', 'error')
            return render_template('login.html'), 200

        login_user(user)
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    Logout user and clear session cookie.

    Returns:
        redirect: 302 to login page
    """
    logout_user()
    return redirect(url_for('auth.login_page'))
