"""
LockIn Dashboard API Routes
CM2211 Group 07 — Internet of Things

Provides analytics endpoints for the web dashboard (F6, F8).
All routes require authentication via session cookie.
"""

import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app import db
from models import Session, Distraction

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


@dashboard_bp.route('/sessions', methods=['GET'])
@login_required
def get_sessions() -> Tuple[Dict[str, Any], int]:
    """
    Get user's sessions, newest first (F6).

    Query params:
        limit (int, default 50): Max sessions to return
        offset (int, default 0): Pagination offset

    Returns:
        JSON: {"sessions": [...], "total": <count>}
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        # Clamp values to prevent abuse
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)

        query = db.session.query(Session).filter_by(user_id=current_user.id).order_by(Session.timestamp.desc())
        total = query.count()

        sessions = query.limit(limit).offset(offset).all()
        logger.debug(f"User {current_user.id} retrieved {len(sessions)} sessions")

        return jsonify({
            'sessions': [
                {
                    'id': s.id,
                    'timestamp': s.timestamp.isoformat() if s.timestamp else None,
                    'duration_mins': s.duration_mins,
                    'distraction_count': s.distraction_count,
                    'focus_score': s.focus_score,
                    'streak_days': s.streak_days
                }
                for s in sessions
            ],
            'total': total
        }), 200
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_sessions: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_sessions: {e}")
        return jsonify({'error': 'internal_error'}), 500


@dashboard_bp.route('/stats/summary', methods=['GET'])
@login_required
def get_summary() -> Tuple[Dict[str, Any], int]:
    """
    Aggregated stats for dashboard header cards (F8).
    Uses SQLAlchemy aggregation for efficiency.

    Returns:
        JSON: {
            "current_streak": int,
            "total_sessions_today": int,
            "total_focus_mins_today": float,
            "avg_focus_score_this_week": float,
            "avg_focus_score_last_week": float,
            "week_over_week_change_pct": float
        }
    """
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        last_week_start = week_start - timedelta(days=7)

        # Today's sessions (optimized with aggregate)
        today_count = db.session.query(func.count(Session.id)).filter(
            Session.user_id == current_user.id,
            Session.timestamp >= today_start
        ).scalar() or 0

        today_mins = db.session.query(func.sum(Session.duration_mins)).filter(
            Session.user_id == current_user.id,
            Session.timestamp >= today_start
        ).scalar() or 0.0

        # Current streak (from most recent session)
        latest_session = db.session.query(Session).filter_by(user_id=current_user.id).order_by(
            Session.timestamp.desc()
        ).first()
        current_streak = latest_session.streak_days if latest_session else 0

        # This week's average (optimized)
        this_week_avg = db.session.query(func.avg(Session.focus_score)).filter(
            Session.user_id == current_user.id,
            Session.timestamp >= week_start
        ).scalar() or 0.0

        # Last week's average (optimized)
        last_week_avg = db.session.query(func.avg(Session.focus_score)).filter(
            Session.user_id == current_user.id,
            Session.timestamp >= last_week_start,
            Session.timestamp < week_start
        ).scalar() or 0.0

        # Week-over-week change
        week_over_week_change = 0.0
        if last_week_avg > 0:
            week_over_week_change = (
                (this_week_avg - last_week_avg) / last_week_avg * 100
            )

        # Best focus score (all-time high)
        best_focus = db.session.query(func.max(Session.focus_score)).filter(
            Session.user_id == current_user.id
        ).scalar() or 0.0

        logger.debug(f"Summary stats retrieved for user {current_user.id}")

        return jsonify({
            'current_streak': current_streak,
            'total_sessions_today': int(today_count),
            'total_focus_mins_today': float(today_mins),
            'avg_focus_score_this_week': round(float(this_week_avg), 1),
            'avg_focus_score_last_week': round(float(last_week_avg), 1),
            'week_over_week_change_pct': round(week_over_week_change, 1),
            'best_focus_score': round(float(best_focus), 1)
        }), 200
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_summary: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_summary: {e}")
        return jsonify({'error': 'internal_error'}), 500


@dashboard_bp.route('/stats/heatmap', methods=['GET'])
@login_required
def get_heatmap() -> Tuple[Dict[str, Any], int]:
    """
    Distraction counts grouped by hour of day (F8).
    Generates insight: "You get distracted most around X:00 PM/AM"

    Returns:
        JSON: {
            "heatmap": [{"hour": 0, "count": 0}, ...],
            "peak_hour": int,
            "insight": str
        }
    """
    try:
        # Get all distractions for user (optimized join)
        distractions = db.session.query(Distraction).join(Session).filter(
            Session.user_id == current_user.id
        ).all()

        # Group by hour
        hour_counts = [0] * 24
        for distraction in distractions:
            try:
                # Use datetime object directly if available
                dt = distraction.timestamp
                if isinstance(dt, str):
                    dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                hour = dt.hour
                hour_counts[hour] += 1
            except (ValueError, AttributeError, TypeError) as e:
                logger.warning(f"Failed to parse distraction timestamp: {e}")
                continue

        peak_hour = hour_counts.index(max(hour_counts)) if max(hour_counts) > 0 else 0

        # Generate insight string
        am_pm = 'AM' if peak_hour < 12 else 'PM'
        display_hour = peak_hour if peak_hour <= 12 else peak_hour - 12
        if display_hour == 0:
            display_hour = 12
        insight = f'You get distracted most around {display_hour}:00 {am_pm}'

        logger.debug(f"Heatmap generated for user {current_user.id}, peak hour: {peak_hour}")

        return jsonify({
            'heatmap': [{'hour': h, 'count': hour_counts[h]} for h in range(24)],
            'peak_hour': peak_hour,
            'insight': insight
        }), 200
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_heatmap: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_heatmap: {e}")
        return jsonify({'error': 'internal_error'}), 500


@dashboard_bp.route('/stats/trend', methods=['GET'])
@login_required
def get_trend() -> Tuple[Dict[str, Any], int]:
    """
    Focus scores over the last N days, one data point per day (F8).
    Uses optimized aggregation queries.

    Query params:
        days (int, default 14): Number of days to return

    Returns:
        JSON: {
            "trend": [
                {"date": "2026-02-24", "avg_focus_score": 61.2, "session_count": 2},
                ...
            ]
        }
    """
    try:
        days = request.args.get('days', 14, type=int)
        days = min(max(days, 1), 90)  # Clamp to 1-90 days
        now = datetime.utcnow()

        trend = []
        for i in range(days):
            date = (now - timedelta(days=i)).date()
            date_start = datetime.combine(date, datetime.min.time())
            date_end = date_start + timedelta(days=1)

            # Use optimized aggregation queries
            avg_focus = db.session.query(func.avg(Session.focus_score)).filter(
                Session.user_id == current_user.id,
                Session.timestamp >= date_start,
                Session.timestamp < date_end
            ).scalar() or 0.0

            session_count = db.session.query(func.count(Session.id)).filter(
                Session.user_id == current_user.id,
                Session.timestamp >= date_start,
                Session.timestamp < date_end
            ).scalar() or 0

            trend.append({
                'date': date.isoformat(),
                'avg_focus_score': round(float(avg_focus), 1),
                'session_count': int(session_count)
            })

        # Reverse to show oldest first
        trend.reverse()
        logger.debug(f"Trend generated for user {current_user.id}, {days} days")

        return jsonify({'trend': trend}), 200
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_trend: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_trend: {e}")
        return jsonify({'error': 'internal_error'}), 500
