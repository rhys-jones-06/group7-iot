"""
LockIn Seed Script
CM2211 Group 07 — Internet of Things

One-off script to create users and generate API keys.
Run once to populate the database with initial users.

Usage:
    python seed.py
"""

import secrets
from app import create_app, db
from models import User


def seed_users():
    """
    Create initial users and generate unique API keys.
    """
    app = create_app()

    with app.app_context():
        # Check if users already exist
        if User.query.first():
            print('Database already contains users. Skipping seed.')
            return

        # Create sample users
        users_data = [
            {'username': 'alice', 'password': 'alice123'},
            {'username': 'bob', 'password': 'bob456'},
            {'username': 'charlie', 'password': 'charlie789'},
        ]

        for user_data in users_data:
            user = User(
                username=user_data['username'],
                api_key=secrets.token_urlsafe(32)  # Generate unique API key
            )
            user.set_password(user_data['password'])
            db.session.add(user)
            print(f'Created user: {user.username}')
            print(f'  Password: {user_data["password"]}')
            print(f'  API Key: {user.api_key}')
            print()

        db.session.commit()
        print('✓ Seed completed successfully')


if __name__ == '__main__':
    seed_users()
