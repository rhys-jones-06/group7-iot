"""
LockIn Data Ingest Route
CM2211 Group 07 — Internet of Things

Receives session data from Pi via POST /api/ingest/session (F6, F8).
Authenticated with X-API-Key header.
"""

from flask import Blueprint, request, jsonify
from app import db
from models import User, Session, Distraction

ingest_bp = Blueprint('ingest', __name__, url_prefix='/api')


def get_user_from_api_key():
    """
    Extract and validate API key from request header.

    Returns:
        User: User instance if valid key found, None otherwise
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return None
    return User.query.filter_by(api_key=api_key).first()


@ingest_bp.route('/ingest/session', methods=['POST'])
def ingest_session():
    """
    Receive a completed Pomodoro session from the Pi.

    Auth: X-API-Key header (Pi authentication)

    Request body (JSON):
        {
            "timestamp": "2026-03-09T14:32:00",
            "duration_mins": 24.5,
            "distraction_count": 3,
            "focus_score": 81.7,
            "streak_days": 5,
            "distractions": [
                { "timestamp": "...", "type": "phone", "confidence": 0.87 },
                { "timestamp": "...", "type": "posture", "confidence": null }
            ]
        }

    Returns:
        JSON response with status code:
            201 Created: {"session_id": <id>}
            400 Bad Request: {"error": "...", "detail": "..."}
            401 Unauthorized: {"error": "unauthorized", "detail": "Invalid API key"}
    """
    # Authenticate Pi via API key
    user = get_user_from_api_key()
    if not user:
        return jsonify({
            'error': 'unauthorized',
            'detail': 'Invalid or missing API key'
        }), 401

    # Validate request body
    data = request.get_json()
    if not data:
        return jsonify({
            'error': 'bad_request',
            'detail': 'Request body must be valid JSON'
        }), 400

    # Check required fields
    required_fields = ['timestamp', 'duration_mins', 'distraction_count', 'focus_score', 'streak_days']
    for field in required_fields:
        if field not in data:
            return jsonify({
                'error': 'missing_field',
                'detail': f'{field} is required'
            }), 400

    # Validate field types
    try:
        timestamp = str(data['timestamp'])
        duration_mins = float(data['duration_mins'])
        distraction_count = int(data['distraction_count'])
        focus_score = float(data['focus_score'])
        streak_days = int(data['streak_days'])
    except (ValueError, TypeError) as e:
        return jsonify({
            'error': 'invalid_field',
            'detail': f'Invalid field type: {str(e)}'
        }), 400

    # Create session
    session = Session(
        user_id=user.id,
        timestamp=timestamp,
        duration_mins=duration_mins,
        distraction_count=distraction_count,
        focus_score=focus_score,
        streak_days=streak_days
    )
    db.session.add(session)
    db.session.flush()  # Get the session ID before committing

    # Add distraction records if present
    if 'distractions' in data and isinstance(data['distractions'], list):
        for distraction_data in data['distractions']:
            try:
                distraction = Distraction(
                    session_id=session.id,
                    timestamp=str(distraction_data.get('timestamp', '')),
                    type=str(distraction_data.get('type', '')),
                    confidence=distraction_data.get('confidence')
                )
                if distraction.confidence is not None:
                    distraction.confidence = float(distraction.confidence)
                db.session.add(distraction)
            except (ValueError, TypeError, KeyError):
                pass  # Skip malformed distraction records

    db.session.commit()

    return jsonify({'session_id': session.id}), 201
