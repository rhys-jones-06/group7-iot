"""
LockIn Dashboard API Routes
CM2211 Group 07 — Internet of Things

Provides analytics endpoints for the web dashboard (F6, F8).
All routes require authentication via session cookie.
"""

import json
import logging
from collections import defaultdict
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Session, Distraction, User

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

        # Current streak — read from User row (authoritative, updated on every ingest)
        user_row = db.session.get(User, current_user.id)
        current_streak = user_row.streak_days if user_row else 0

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
        # Single GROUP BY query — no Python-side row iteration
        rows = (
            db.session.query(
                func.strftime('%H', Distraction.timestamp).label('hour'),
                func.count(Distraction.id).label('count'),
            )
            .join(Session, Distraction.session_id == Session.id)
            .filter(Session.user_id == current_user.id)
            .group_by(func.strftime('%H', Distraction.timestamp))
            .all()
        )
        hour_counts = [0] * 24
        for row in rows:
            hour_counts[int(row.hour)] = int(row.count)

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
        days   = min(max(request.args.get('days', 14, type=int), 1), 90)
        now    = datetime.utcnow()
        cutoff = now - timedelta(days=days)

        # Single GROUP BY query replacing the previous N*2 per-day loop
        rows = (
            db.session.query(
                func.strftime('%Y-%m-%d', Session.timestamp).label('date'),
                func.avg(Session.focus_score).label('avg_focus'),
                func.count(Session.id).label('session_count'),
            )
            .filter(
                Session.user_id == current_user.id,
                Session.timestamp >= cutoff,
            )
            .group_by(func.strftime('%Y-%m-%d', Session.timestamp))
            .all()
        )
        row_map = {row.date: row for row in rows}

        # Build full date range, filling zeros for days with no sessions
        trend = []
        for i in range(days - 1, -1, -1):
            date_str = (now - timedelta(days=i)).date().isoformat()
            row      = row_map.get(date_str)
            trend.append({
                'date':            date_str,
                'avg_focus_score': round(float(row.avg_focus), 1) if row else 0.0,
                'session_count':   int(row.session_count)         if row else 0,
            })

        logger.debug(f"Trend generated for user {current_user.id}, {days} days")
        return jsonify({'trend': trend}), 200
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_trend: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_trend: {e}")
        return jsonify({'error': 'internal_error'}), 500


@dashboard_bp.route('/leaderboard', methods=['GET'])
@login_required
def get_leaderboard() -> Tuple[Dict[str, Any], int]:
    """
    Top 10 users ranked by composite score: SUM(duration_mins) * AVG(focus_score).
    Rewards both total time invested and focus quality.

    Returns:
        JSON: {
            "leaderboard": [
                {"rank": 1, "username": "...", "score": 12450, "total_mins": 150, "avg_focus": 83.0, "is_me": false},
                ...
            ],
            "current_user": "<username>"
        }
    """
    try:
        rows = (
            db.session.query(
                User.username,
                func.round(func.sum(Session.duration_mins), 1).label('total_mins'),
                func.round(func.avg(Session.focus_score), 1).label('avg_focus'),
                func.count(Session.id).label('session_count'),
            )
            .join(Session, User.id == Session.user_id)
            .group_by(User.id, User.username)
            .order_by(
                (func.sum(Session.duration_mins) * func.avg(Session.focus_score)).desc()
            )
            .limit(10)
            .all()
        )

        leaderboard = []
        for i, row in enumerate(rows):
            total_mins = float(row.total_mins or 0)
            avg_focus  = float(row.avg_focus  or 0)
            leaderboard.append({
                'rank':       i + 1,
                'username':   row.username,
                'score':      round(total_mins * avg_focus),
                'total_mins': round(total_mins),
                'avg_focus':  round(avg_focus, 1),
                'sessions':   int(row.session_count),
                'is_me':      row.username == current_user.username,
            })

        # If current user has no sessions, append them at the bottom unranked
        me_in_list = any(e['is_me'] for e in leaderboard)
        if not me_in_list:
            leaderboard.append({
                'rank':       len(leaderboard) + 1,
                'username':   current_user.username,
                'score':      0,
                'total_mins': 0,
                'avg_focus':  0.0,
                'sessions':   0,
                'is_me':      True,
            })

        logger.debug(f"Leaderboard fetched by user {current_user.id}, {len(leaderboard)} entries")
        return jsonify({'leaderboard': leaderboard, 'current_user': current_user.username}), 200

    except SQLAlchemyError as e:
        logger.error(f"Database error in get_leaderboard: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_leaderboard: {e}")
        return jsonify({'error': 'internal_error'}), 500


@dashboard_bp.route('/stats/all-time', methods=['GET'])
@login_required
def get_all_time_stats() -> Tuple[Dict[str, Any], int]:
    """All-time aggregate stats for the current user."""
    try:
        uid = current_user.id
        total_sessions = db.session.query(func.count(Session.id)).filter(Session.user_id == uid).scalar() or 0
        total_mins = db.session.query(func.sum(Session.duration_mins)).filter(Session.user_id == uid).scalar() or 0.0
        avg_focus = db.session.query(func.avg(Session.focus_score)).filter(Session.user_id == uid).scalar() or 0.0
        avg_duration = db.session.query(func.avg(Session.duration_mins)).filter(Session.user_id == uid).scalar() or 0.0
        total_distr = (
            db.session.query(func.count(Distraction.id))
            .join(Session, Distraction.session_id == Session.id)
            .filter(Session.user_id == uid)
            .scalar() or 0
        )
        user_row = db.session.get(User, uid)
        best_streak = getattr(user_row, 'best_streak_days', 0) if user_row else 0

        return jsonify({
            'total_sessions': int(total_sessions),
            'total_focus_mins': round(float(total_mins), 1),
            'avg_focus_score': round(float(avg_focus), 1),
            'avg_session_mins': round(float(avg_duration), 1),
            'total_distractions': int(total_distr),
            'best_streak_days': int(best_streak),
        }), 200
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_all_time_stats: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_all_time_stats: {e}")
        return jsonify({'error': 'internal_error'}), 500


@dashboard_bp.route('/stats/breakdown', methods=['GET'])
@login_required
def get_breakdown() -> Tuple[Dict[str, Any], int]:
    """Distraction type counts and per-day-of-week focus averages."""
    try:
        uid = current_user.id
        phone_count = (
            db.session.query(func.count(Distraction.id))
            .join(Session, Distraction.session_id == Session.id)
            .filter(Session.user_id == uid, Distraction.type == 'phone')
            .scalar() or 0
        )
        posture_count = (
            db.session.query(func.count(Distraction.id))
            .join(Session, Distraction.session_id == Session.id)
            .filter(Session.user_id == uid, Distraction.type == 'posture')
            .scalar() or 0
        )

        sessions = db.session.query(Session).filter(Session.user_id == uid).all()
        day_scores: dict = defaultdict(list)
        for s in sessions:
            day_scores[s.timestamp.weekday()].append(s.focus_score)

        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        by_day = [
            {
                'day': days[i],
                'avg_focus': round(sum(day_scores[i]) / len(day_scores[i]), 1) if day_scores[i] else 0.0,
                'count': len(day_scores[i]),
            }
            for i in range(7)
        ]

        return jsonify({'by_type': {'phone': int(phone_count), 'posture': int(posture_count)}, 'by_day': by_day}), 200
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_breakdown: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_breakdown: {e}")
        return jsonify({'error': 'internal_error'}), 500


@dashboard_bp.route('/pet', methods=['GET'])
@login_required
def get_pet() -> Tuple[Dict[str, Any], int]:
    """Return the current user's virtual pet state (F8)."""
    try:
        user = db.session.get(User, current_user.id)
        health    = round(float(user.pet_health    or 85.0), 1)
        happiness = round(float(user.pet_happiness or 90.0), 1)
        if happiness >= 80:
            mood, emoji = 'happy',   '🐊'
        elif happiness >= 50:
            mood, emoji = 'content', '😐'
        else:
            mood, emoji = 'sad',     '😢'
        return jsonify({
            'health':    health,
            'happiness': happiness,
            'mood':      mood,
            'emoji':     emoji,
        }), 200
    except Exception as e:
        logger.error(f"Error in get_pet: {e}")
        return jsonify({'error': 'internal_error'}), 500


@dashboard_bp.route('/dashboard/layout', methods=['GET'])
@login_required
def get_layout() -> Tuple[Dict[str, Any], int]:
    """Return the user's saved dashboard widget layout (empty list = use default)."""
    from models import DashboardLayout
    try:
        row = db.session.query(DashboardLayout).filter_by(user_id=current_user.id).first()
        layout = json.loads(row.layout_json) if row else []
        return jsonify({'layout': layout}), 200
    except Exception as e:
        logger.error(f"Error in get_layout: {e}")
        return jsonify({'layout': []}), 200


@dashboard_bp.route('/dashboard/layout', methods=['PUT'])
@login_required
def save_layout() -> Tuple[Dict[str, Any], int]:
    """Persist the user's dashboard widget layout."""
    from models import DashboardLayout
    try:
        data = request.get_json()
        if not data or 'layout' not in data:
            return jsonify({'error': 'bad_request'}), 400

        layout_json = json.dumps(data['layout'])
        row = db.session.query(DashboardLayout).filter_by(user_id=current_user.id).first()
        if row:
            row.layout_json = layout_json
        else:
            row = DashboardLayout(user_id=current_user.id, layout_json=layout_json)
            db.session.add(row)
        db.session.commit()
        return jsonify({'status': 'saved'}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error in save_layout: {e}")
        return jsonify({'error': 'database_error'}), 500
    except Exception as e:
        logger.error(f"Error in save_layout: {e}")
        return jsonify({'error': 'internal_error'}), 500
