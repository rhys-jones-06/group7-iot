"""
LockIn Settings Routes
CM2211 Group 07 — Internet of Things

Web settings page (cookie auth) and device settings API (X-API-Key auth).
"""

import logging
from typing import Tuple, Union, Dict, Any
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from extensions import db

settings_bp = Blueprint('settings', __name__)
logger = logging.getLogger(__name__)


def _get_or_create_settings(user_id: int):
    from models import UserSettings
    s = db.session.query(UserSettings).filter_by(user_id=user_id).first()
    if not s:
        s = UserSettings(user_id=user_id)
        db.session.add(s)
        db.session.commit()
    return s


@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page() -> Union[str, Tuple[str, int]]:
    """Render and handle the settings page."""
    settings = _get_or_create_settings(current_user.id)

    if request.method == 'POST':
        try:
            def clamp(val, lo, hi):
                return max(lo, min(hi, val))

            settings.session_duration_mins      = clamp(int(request.form.get('session_duration_mins', 25)), 5, 90)
            settings.short_break_mins           = clamp(int(request.form.get('short_break_mins', 5)), 1, 30)
            settings.long_break_mins            = clamp(int(request.form.get('long_break_mins', 15)), 5, 60)
            settings.sessions_before_long_break = clamp(int(request.form.get('sessions_before_long_break', 4)), 1, 10)
            settings.phone_detection_enabled    = request.form.get('phone_detection_enabled') == 'on'
            settings.posture_detection_enabled  = request.form.get('posture_detection_enabled') == 'on'
            settings.phone_sensitivity          = clamp(float(request.form.get('phone_sensitivity', 0.7)), 0.1, 1.0)
            settings.alert_type                 = request.form.get('alert_type', 'both')
            settings.alert_cooldown_secs        = clamp(int(request.form.get('alert_cooldown_secs', 30)), 5, 300)

            db.session.commit()
            logger.info(f"Settings updated for user {current_user.id}")
            flash('Settings saved!', 'success')
        except (ValueError, TypeError) as e:
            db.session.rollback()
            logger.warning(f"Settings validation error for user {current_user.id}: {e}")
            flash('Invalid value in settings — please check your inputs.', 'error')
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"DB error saving settings for user {current_user.id}: {e}")
            flash('Could not save settings. Please try again.', 'error')

        return redirect(url_for('settings.settings_page'))

    return render_template('settings.html', settings=settings, username=current_user.username)


@settings_bp.route('/api/settings', methods=['GET'])
def get_settings_api() -> Tuple[Dict[str, Any], int]:
    """
    Return device settings as JSON.

    Supports two auth methods so the Pi can call this on startup:
      - Session cookie  (browser / logged-in user)
      - X-API-Key header (Pi device)
    """
    from models import User, UserSettings
    from flask_login import current_user as cu

    user = None

    # Try API key first (device auth)
    api_key = request.headers.get('X-API-Key')
    if api_key:
        try:
            user = db.session.query(User).filter_by(api_key=api_key).first()
        except SQLAlchemyError as e:
            logger.error(f"DB error during API key lookup: {e}")
            return jsonify({'error': 'database_error'}), 500

    # Fall back to session cookie
    if user is None and cu.is_authenticated:
        user = cu

    if user is None:
        return jsonify({'error': 'unauthorized', 'detail': 'Provide X-API-Key header or log in'}), 401

    settings = _get_or_create_settings(user.id)
    return jsonify(settings.to_dict()), 200
