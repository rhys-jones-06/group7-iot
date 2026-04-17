"""
LockIn Configuration Management
CM2211 Group 07 — Internet of Things

Environment-based configuration for Flask application.
"""

import os
from datetime import timedelta


class Config:
    """Base configuration — shared across all environments."""

    # Flask
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-key-change-in-production')
    DEBUG = False
    TESTING = False

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///lockin.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
    }

    # Flask-Login
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True

    # API Rate Limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "200/hour"
    RATELIMIT_STORAGE_URL = "memory://"

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


class DevelopmentConfig(Config):
    """Development environment configuration."""

    DEBUG = True
    SQLALCHEMY_ECHO = True
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production environment configuration."""

    DEBUG = False
    SQLALCHEMY_ECHO = False


class TestingConfig(Config):
    """Testing environment configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    RATELIMIT_ENABLED = False


# Config selector
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}


def get_config():
    """Get configuration based on FLASK_ENV environment variable."""
    env = os.environ.get('FLASK_ENV', 'development')
    return config_by_name.get(env, DevelopmentConfig)
