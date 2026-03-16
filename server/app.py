"""
LockIn Web Server — Flask Application Entry Point

This module initializes the Flask app, configures the database,
and registers all routes (auth, ingest, dashboard).
"""

import os
from flask import Flask, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, current_user

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    """
    Flask application factory. Creates and configures the Flask app instance.

    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get(
        'FLASK_SECRET_KEY',
        'dev-key-change-in-production'
    )
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'sqlite:///lockin.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_page'

    # Create database tables within app context
    with app.app_context():
        db.create_all()

    # Register blueprints (routes)
    from routes.auth import auth_bp
    from routes.ingest import ingest_bp
    from routes.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(dashboard_bp)

    # Main dashboard route (F6: Custom web dashboard)
    @app.route('/', methods=['GET'])
    @login_required
    def dashboard():
        """Serve the main dashboard HTML."""
        return render_template('dashboard.html', username=current_user.username)

    # Redirect /login to /login if already authenticated
    @app.route('/login', methods=['GET'])
    def login_redirect():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('auth.login_page'))

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
