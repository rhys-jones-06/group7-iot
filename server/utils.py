"""
LockIn Utility Functions
CM2211 Group 07 — Internet of Things

Common helper functions for the application.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def serialize_session(session: Any) -> Dict[str, Any]:
    """
    Serialize a Session model instance to a JSON-safe dictionary.

    Args:
        session: Session model instance

    Returns:
        dict: Serialized session data
    """
    return {
        'id': session.id,
        'timestamp': session.timestamp.isoformat() if session.timestamp else None,
        'duration_mins': session.duration_mins,
        'distraction_count': session.distraction_count,
        'focus_score': session.focus_score,
        'streak_days': session.streak_days
    }


def serialize_distraction(distraction: Any) -> Dict[str, Any]:
    """
    Serialize a Distraction model instance to a JSON-safe dictionary.

    Args:
        distraction: Distraction model instance

    Returns:
        dict: Serialized distraction data
    """
    return {
        'id': distraction.id,
        'session_id': distraction.session_id,
        'timestamp': distraction.timestamp.isoformat() if distraction.timestamp else None,
        'type': distraction.type,
        'confidence': distraction.confidence
    }


def format_hour_for_display(hour: int) -> str:
    """
    Convert 24-hour format to 12-hour display format.

    Args:
        hour: Hour in 24-hour format (0-23)

    Returns:
        str: Formatted hour string (e.g., "3:00 PM")
    """
    am_pm = 'AM' if hour < 12 else 'PM'
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:00 {am_pm}"


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value between min and max.

    Args:
        value: Value to clamp
        min_val: Minimum value
        max_val: Maximum value

    Returns:
        float: Clamped value
    """
    return max(min_val, min(value, max_val))
