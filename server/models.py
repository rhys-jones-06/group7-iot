"""
LockIn Database Models
CM2211 Group 07 — Internet of Things

Defines SQLAlchemy ORM models for users, sessions, and distractions (F6, F8).
"""

from datetime import datetime
from typing import List, Optional
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(UserMixin, db.Model):
    """
    User model — one row per registered user / Pi device (F6).

    Attributes:
        id: Primary key (auto-increment)
        username: Unique username
        password_hash: Hashed password (werkzeug.security)
        api_key: Unique key for Pi authentication (X-API-Key header)
        streak_days: Current consecutive study session streak
        last_session_date: Date of last completed session (for streak tracking)
        pet_health: Virtual pet health (0-100)
        pet_happiness: Virtual pet happiness (0-100)
    """
    __tablename__ = 'users'

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), nullable=False, unique=True, index=True)
    password_hash: str = db.Column(db.String(255), nullable=False)
    api_key: str = db.Column(db.String(255), nullable=False, unique=True, index=True)
    streak_days: int = db.Column(db.Integer, nullable=False, default=0)
    last_session_date: datetime = db.Column(db.Date, nullable=True)
    pet_health: float = db.Column(db.Float, nullable=False, default=85.0)
    pet_happiness: float = db.Column(db.Float, nullable=False, default=90.0)
    best_streak_days: int = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    sessions = db.relationship(
        'Session',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def set_password(self, password: str) -> None:
        """Hash and store password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check password against hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f'<User {self.username}>'


class Session(db.Model):
    """
    Session model — one row per completed Pomodoro session (F6, F8).

    Attributes:
        id: Primary key (auto-increment)
        user_id: Foreign key to User
        timestamp: Session end time (UTC)
        duration_mins: Actual focus time (may be < 25 if abandoned)
        distraction_count: Total distractions in session
        focus_score: Normalized 0-100: duration / (distraction_count + 1)
        streak_days: Current streak at time of session completion
    """
    __tablename__ = 'sessions'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True
    )
    timestamp: datetime = db.Column(db.DateTime, nullable=False, index=True, default=datetime.utcnow)
    duration_mins: float = db.Column(db.Float, nullable=False)
    distraction_count: int = db.Column(db.Integer, nullable=False)
    focus_score: float = db.Column(db.Float, nullable=False)
    streak_days: int = db.Column(db.Integer, nullable=False)

    # Relationships
    distractions = db.relationship(
        'Distraction',
        backref='session',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def __repr__(self) -> str:
        return f'<Session {self.id} user={self.user_id} at {self.timestamp}>'


class Distraction(db.Model):
    """
    Distraction model — one row per individual distraction event (F8).

    Attributes:
        id: Primary key (auto-increment)
        session_id: Foreign key to Session
        timestamp: Distraction detection time (UTC)
        type: 'phone' (F2) or 'posture' (F3)
        confidence: Confidence score (null for posture type)
    """
    __tablename__ = 'distractions'

    id: int = db.Column(db.Integer, primary_key=True)
    session_id: int = db.Column(
        db.Integer,
        db.ForeignKey('sessions.id'),
        nullable=False,
        index=True
    )
    timestamp: datetime = db.Column(db.DateTime, nullable=False, index=True, default=datetime.utcnow)
    type: str = db.Column(db.String(20), nullable=False)  # 'phone' or 'posture'
    confidence: Optional[float] = db.Column(db.Float, nullable=True)  # None for posture type

    def __repr__(self) -> str:
        return f'<Distraction {self.id} session={self.session_id} type={self.type}>'


class UserProfile(db.Model):
    """
    User demographic/onboarding survey data.
    One row per user, created after the post-registration survey.
    """
    __tablename__ = 'user_profiles'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    age: Optional[int] = db.Column(db.Integer, nullable=True)
    occupation_type: Optional[str] = db.Column(db.String(20), nullable=True)  # 'student', 'professional', 'both', 'other'
    institution: Optional[str] = db.Column(db.String(200), nullable=True)
    year_of_study: Optional[int] = db.Column(db.Integer, nullable=True)
    field_of_study: Optional[str] = db.Column(db.String(200), nullable=True)
    job_title: Optional[str] = db.Column(db.String(200), nullable=True)
    daily_study_hours: Optional[float] = db.Column(db.Float, nullable=True)
    study_goals: Optional[str] = db.Column(db.Text, nullable=True)
    completed_at: datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f'<UserProfile user={self.user_id} occupation={self.occupation_type}>'


class UserSettings(db.Model):
    """
    Per-user device + app settings.
    Consumed by the Pi via GET /api/settings (X-API-Key auth).
    """
    __tablename__ = 'user_settings'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)

    # Pomodoro timer
    session_duration_mins: int = db.Column(db.Integer, nullable=False, default=25)
    short_break_mins: int = db.Column(db.Integer, nullable=False, default=5)
    long_break_mins: int = db.Column(db.Integer, nullable=False, default=15)
    sessions_before_long_break: int = db.Column(db.Integer, nullable=False, default=4)

    # Detection toggles
    phone_detection_enabled: bool = db.Column(db.Boolean, nullable=False, default=True)
    posture_detection_enabled: bool = db.Column(db.Boolean, nullable=False, default=True)

    # Sensitivity (0.0 = very sensitive / triggers easily, 1.0 = very strict)
    phone_sensitivity: float = db.Column(db.Float, nullable=False, default=0.7)

    # Alerts
    alert_type: str = db.Column(db.String(20), nullable=False, default='both')  # 'visual', 'audio', 'both'
    alert_cooldown_secs: int = db.Column(db.Integer, nullable=False, default=30)

    updated_at: datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'session_duration_mins': self.session_duration_mins,
            'short_break_mins': self.short_break_mins,
            'long_break_mins': self.long_break_mins,
            'sessions_before_long_break': self.sessions_before_long_break,
            'phone_detection_enabled': self.phone_detection_enabled,
            'posture_detection_enabled': self.posture_detection_enabled,
            'phone_sensitivity': self.phone_sensitivity,
            'alert_type': self.alert_type,
            'alert_cooldown_secs': self.alert_cooldown_secs,
        }

    def __repr__(self) -> str:
        return f'<UserSettings user={self.user_id}>'


class DashboardLayout(db.Model):
    """Per-user dashboard widget layout stored as JSON."""
    __tablename__ = 'dashboard_layouts'

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    layout_json: str = db.Column(db.Text, nullable=False, default='[]')
    updated_at: datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f'<DashboardLayout user={self.user_id}>'
