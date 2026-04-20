"""
LockIn Web Server — Flask Application Entry Point
CM2211 Group 07 — Internet of Things

Initializes the Flask app, configures the database, and registers routes.
"""

import logging
import os
from typing import Tuple
from flask import Flask, render_template, redirect, url_for
from flask_login import login_required, current_user

from config import get_config
from extensions import db, login_manager, limiter

# Configure logging
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """
    Flask application factory. Creates and configures the Flask app instance.

    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    # Load configuration
    config = get_config()
    app.config.from_object(config)

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT
    )
    logger.info(f"Initializing LockIn server in {config.__class__.__name__}")

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = 'auth.login_page'

    # Register user_loader callback for Flask-Login
    @login_manager.user_loader
    def load_user(user_id: str):
        """Load user by ID from database."""
        from models import User
        return db.session.get(User, int(user_id))

    # Register blueprints (routes)
    from routes.auth import auth_bp
    from routes.ingest import ingest_bp
    from routes.dashboard import dashboard_bp
    from routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(settings_bp)
    logger.info("Blueprints registered")

    # Create database tables within app context (models must be imported first)
    with app.app_context():
        import models  # noqa: F401 — ensures tables are registered before create_all
        db.create_all()
        logger.info("Database tables initialized")

    # Main dashboard route (F6: Custom web dashboard)
    @app.route('/', methods=['GET'])
    @login_required
    def dashboard() -> Tuple[str, int]:
        """Serve the main dashboard HTML."""
        logger.debug(f"Dashboard accessed by user {current_user.id}")
        return render_template('dashboard.html', username=current_user.username), 200

    # Error handlers
    @app.errorhandler(429)
    def ratelimit_handler(e):
        """Handle rate limiting errors."""
        logger.warning(f"Rate limit exceeded: {e}")
        return {'error': 'rate_limited', 'detail': 'Too many requests'}, 429

    @app.errorhandler(500)
    def internal_error(e):
        """Handle internal server errors."""
        logger.error(f"Internal server error: {e}")
        return {'error': 'internal_error', 'detail': 'An unexpected error occurred'}, 500

    return app


if __name__ == '__main__':
    app = create_app()
    logger.info("Starting LockIn server")
    app.run(
        debug=app.config['DEBUG'],
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000))
    )
