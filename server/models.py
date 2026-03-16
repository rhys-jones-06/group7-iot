"""
LockIn Database Models
CM2211 Group 07 — Internet of Things

Defines SQLAlchemy ORM models for users, sessions, and distractions (F6, F8).
"""

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


class User(UserMixin, db.Model):
    """
    User model — one row per registered user / Pi device (F6).

    Attributes:
        id: Primary key (auto-increment)
        username: Unique username
        password_hash: Hashed password (werkzeug.security)
        api_key: Unique key for Pi authentication (X-API-Key header)
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(255), nullable=False, unique=True)

    # Relationships
    sessions = db.relationship('Session', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        """Hash and store password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check password against hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Session(db.Model):
    """
    Session model — one row per completed Pomodoro session (F6, F8).

    Attributes:
        id: Primary key (auto-increment)
        user_id: Foreign key to User
        timestamp: ISO 8601 session end time
        duration_mins: Actual focus time (may-be < 25 if abandoned)
        distraction_count: Total distractions in session
        focus_score: Normalized 0-100: duration / (distraction_count + 1)
        streak_days: Current streak at time of session completion
    """
    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.String(30), nullable=False)  # ISO 8601 string
    duration_mins = db.Column(db.Float, nullable=False)
    distraction_count = db.Column(db.Integer, nullable=False)
    focus_score = db.Column(db.Float, nullable=False)
    streak_days = db.Column(db.Integer, nullable=False)

    # Relationships
    distractions = db.relationship('Distraction', backref='session', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Session {self.id} user={self.user_id} at {self.timestamp}>'


class Distraction(db.Model):
    """
    Distraction model — one row per individual distraction event (F8).

    Attributes:
        id: Primary key (auto-increment)
        session_id: Foreign key to Session
        timestamp: ISO 8601 distraction detection time
        type: 'phone' (F2) or 'posture' (F3)
        confidence: Confidence score (null for posture type)
    """
    __tablename__ = 'distractions'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    timestamp = db.Column(db.String(30), nullable=False)  # ISO 8601 string
    type = db.Column(db.String(20), nullable=False)  # 'phone' or 'posture'
    confidence = db.Column(db.Float, nullable=True)  # None for posture type

    def __repr__(self):
        return f'<Distraction {self.id} session={self.session_id} type={self.type}>'


@login_manager.user_loader
def load_user(user_id):
    """
    Flask-Login callback to load a user by ID from the database.

    Args:
        user_id: User ID from session cookie

    Returns:
        User: User instance or None if not found
    """
    return User.query.get(int(user_id))
