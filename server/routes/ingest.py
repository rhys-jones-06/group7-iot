"""
LockIn Data Ingest Route
CM2211 Group 07 — Internet of Things

Receives session data from Pi via POST /api/ingest/session (F6, F8).
Authenticated with X-API-Key header.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db, limiter
from models import User, Session, Distraction
from validators import SessionIngestSchema, validate_json_request

ingest_bp = Blueprint('ingest', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


def get_user_from_api_key() -> Optional[User]:
    """
    Extract and validate API key from request header.

    Returns:
        User: User instance if valid key found, None otherwise
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return None

    try:
        return User.query.filter_by(api_key=api_key).first()
    except SQLAlchemyError as e:
        logger.error(f"Database error during API key lookup: {e}")
        return None


@ingest_bp.route('/ingest/session', methods=['POST'])
@limiter.limit("100/hour")
def ingest_session() -> Tuple[Dict[str, Any], int]:
    """
    Receive a completed Pomodoro session from the Pi (F6, F8).

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
            500 Internal Server Error: on database error
    """
    # Authenticate Pi via API key
    user = get_user_from_api_key()
    if not user:
        logger.warning(f"Ingest request with invalid API key from {request.remote_addr}")
        return jsonify({
            'error': 'unauthorized',
            'detail': 'Invalid or missing API key'
        }), 401

    # Validate request body structure
    data = request.get_json()
    if not data:
        logger.warning(f"Ingest request with invalid JSON from user {user.id}")
        return jsonify({
            'error': 'bad_request',
            'detail': 'Request body must be valid JSON'
        }), 400

    # Validate against schema
    schema = SessionIngestSchema()
    validated, errors = validate_json_request(schema, data)

    if errors:
        logger.warning(f"Ingest validation failed for user {user.id}: {errors}")
        return jsonify({
            'error': 'validation_error',
            'detail': errors
        }), 400

    try:
        # Create session (F6)
        session = Session(
            user_id=user.id,
            timestamp=validated['timestamp'],
            duration_mins=validated['duration_mins'],
            distraction_count=validated['distraction_count'],
            focus_score=validated['focus_score'],
            streak_days=validated['streak_days']
        )
        db.session.add(session)
        db.session.flush()  # Get the session ID before committing

        # Add distraction records (F8)
        distraction_count = 0
        for distraction_data in validated.get('distractions', []):
            try:
                distraction = Distraction(
                    session_id=session.id,
                    timestamp=distraction_data['timestamp'],
                    type=distraction_data['type'],
                    confidence=distraction_data.get('confidence')
                )
                db.session.add(distraction)
                distraction_count += 1
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Skipped malformed distraction: {e}")
                continue

        db.session.commit()
        logger.info(
            f"Session {session.id} ingested for user {user.id} "
            f"({validated['duration_mins']}min, {distraction_count} distractions)"
        )

        return jsonify({'session_id': session.id}), 201

    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Database integrity error during ingest: {e}")
        return jsonify({
            'error': 'database_error',
            'detail': 'Failed to save session'
        }), 500

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error during ingest: {e}")
        return jsonify({
            'error': 'database_error',
            'detail': 'An unexpected database error occurred'
        }), 500

    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error during ingest: {e}")
        return jsonify({
            'error': 'internal_error',
            'detail': 'An unexpected error occurred'
        }), 500
