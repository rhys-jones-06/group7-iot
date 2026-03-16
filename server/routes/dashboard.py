"""
LockIn Dashboard API Routes
CM2211 Group 07 — Internet of Things

Provides analytics endpoints for the web dashboard (F6, F8).
All routes require authentication via session cookie.
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func
from app import db
from models import Session, Distraction

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api')


@dashboard_bp.route('/sessions', methods=['GET'])
@login_required
def get_sessions():
    """
    Get user's sessions, newest first.

    Query params:
        limit (int, default 50): Max sessions to return
        offset (int, default 0): Pagination offset

    Returns:
        JSON: {"sessions": [...], "total": <count>}
    """
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    query = Session.query.filter_by(user_id=current_user.id).order_by(Session.timestamp.desc())
    total = query.count()

    sessions = query.limit(limit).offset(offset).all()

    return jsonify({
        'sessions': [
            {
                'id': s.id,
                'timestamp': s.timestamp,
                'duration_mins': s.duration_mins,
                'distraction_count': s.distraction_count,
                'focus_score': s.focus_score,
                'streak_days': s.streak_days
            }
            for s in sessions
        ],
        'total': total
    }), 200


@dashboard_bp.route('/stats/summary', methods=['GET'])
@login_required
def get_summary():
    """
    Aggregated stats for dashboard header cards (F8).

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
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    last_week_start = week_start - timedelta(days=7)

    # Today's sessions
    today_sessions = Session.query.filter(
        Session.user_id == current_user.id,
        Session.timestamp >= today_start.isoformat()
    ).all()

    total_sessions_today = len(today_sessions)
    total_focus_mins_today = sum(s.duration_mins for s in today_sessions)

    # Current streak (from most recent session)
    latest_session = Session.query.filter_by(user_id=current_user.id).order_by(
        Session.timestamp.desc()
    ).first()
    current_streak = latest_session.streak_days if latest_session else 0

    # This week's average focus score
    this_week_sessions = Session.query.filter(
        Session.user_id == current_user.id,
        Session.timestamp >= week_start.isoformat()
    ).all()
    avg_focus_this_week = (
        sum(s.focus_score for s in this_week_sessions) / len(this_week_sessions)
        if this_week_sessions else 0.0
    )

    # Last week's average focus score
    last_week_sessions = Session.query.filter(
        Session.user_id == current_user.id,
        Session.timestamp >= last_week_start.isoformat(),
        Session.timestamp < week_start.isoformat()
    ).all()
    avg_focus_last_week = (
        sum(s.focus_score for s in last_week_sessions) / len(last_week_sessions)
        if last_week_sessions else 0.0
    )

    # Week-over-week change
    week_over_week_change = 0.0
    if avg_focus_last_week > 0:
        week_over_week_change = (
            (avg_focus_this_week - avg_focus_last_week) / avg_focus_last_week * 100
        )

    return jsonify({
        'current_streak': current_streak,
        'total_sessions_today': total_sessions_today,
        'total_focus_mins_today': total_focus_mins_today,
        'avg_focus_score_this_week': round(avg_focus_this_week, 1),
        'avg_focus_score_last_week': round(avg_focus_last_week, 1),
        'week_over_week_change_pct': round(week_over_week_change, 1)
    }), 200


@dashboard_bp.route('/stats/heatmap', methods=['GET'])
@login_required
def get_heatmap():
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
    # Get all distractions for user
    distractions = db.session.query(Distraction).join(Session).filter(
        Session.user_id == current_user.id
    ).all()

    # Group by hour
    hour_counts = [0] * 24
    for distraction in distractions:
        try:
            # Parse ISO 8601 timestamp
            dt = datetime.fromisoformat(distraction.timestamp.replace('Z', '+00:00'))
            hour = dt.hour
            hour_counts[hour] += 1
        except (ValueError, AttributeError):
            pass

    peak_hour = hour_counts.index(max(hour_counts)) if max(hour_counts) > 0 else 0

    # Generate insight string
    am_pm = 'AM' if peak_hour < 12 else 'PM'
    display_hour = peak_hour if peak_hour <= 12 else peak_hour - 12
    if display_hour == 0:
        display_hour = 12
    insight = f'You get distracted most around {display_hour}:00 {am_pm}'

    return jsonify({
        'heatmap': [{'hour': h, 'count': hour_counts[h]} for h in range(24)],
        'peak_hour': peak_hour,
        'insight': insight
    }), 200


@dashboard_bp.route('/stats/trend', methods=['GET'])
@login_required
def get_trend():
    """
    Focus scores over the last N days, one data point per day (F8).

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
    days = request.args.get('days', 14, type=int)
    now = datetime.utcnow()

    trend = []
    for i in range(days):
        date = (now - timedelta(days=i)).date()
        date_start = datetime.combine(date, datetime.min.time()).isoformat()
        date_end = datetime.combine(date + timedelta(days=1), datetime.min.time()).isoformat()

        day_sessions = Session.query.filter(
            Session.user_id == current_user.id,
            Session.timestamp >= date_start,
            Session.timestamp < date_end
        ).all()

        avg_focus = (
            sum(s.focus_score for s in day_sessions) / len(day_sessions)
            if day_sessions else 0.0
        )

        trend.append({
            'date': date.isoformat(),
            'avg_focus_score': round(avg_focus, 1),
            'session_count': len(day_sessions)
        })

    # Reverse to show oldest first
    trend.reverse()

    return jsonify({'trend': trend}), 200
