"""
HTTP client for communicating with the LockIn server.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class LockInClient:
    def __init__(self, server_url: str, api_key: str, timeout: int = 10):
        self.base    = server_url.rstrip('/')
        self.headers = {'X-API-Key': api_key, 'Content-Type': 'application/json'}
        self.timeout = timeout
        self.verify  = False  # Cardiff OpenShift uses a CA not trusted by Bullseye

    # ── Settings ──────────────────────────────────────────────────────────
    def get_settings(self) -> Dict[str, Any]:
        """Fetch user settings from the server. Returns defaults on failure."""
        try:
            r = requests.get(
                f'{self.base}/api/settings',
                headers=self.headers,
                timeout=self.timeout,
                verify=self.verify,
            )
            r.raise_for_status()
            settings = r.json()
            logger.info('Settings loaded from server')
            return settings
        except requests.RequestException as e:
            logger.warning(f'Could not fetch settings ({e}), using defaults')
            return {
                'session_duration_mins':      25,
                'short_break_mins':           5,
                'long_break_mins':            15,
                'sessions_before_long_break': 4,
                'phone_detection_enabled':    True,
                'posture_detection_enabled':  True,
                'phone_sensitivity':          0.7,
                'alert_type':                 'both',
                'alert_cooldown_secs':        30,
            }

    # ── Session submission ─────────────────────────────────────────────────
    def submit_session(
        self,
        duration_mins: float,
        distraction_count: int,
        focus_score: float,
        streak_days: int,
        distractions: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[int]:
        """
        POST a completed session to the server.
        Returns the session_id on success, None on failure.
        """
        payload = {
            'timestamp':         datetime.utcnow().isoformat(),
            'duration_mins':     round(duration_mins, 2),
            'distraction_count': distraction_count,
            'focus_score':       round(focus_score, 1),
            'streak_days':       streak_days,
            'distractions':      distractions or [],
        }
        try:
            r = requests.post(
                f'{self.base}/api/ingest/session',
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
                verify=self.verify,
            )
            r.raise_for_status()
            session_id = r.json().get('session_id')
            logger.info(f'Session submitted — id={session_id}')
            return session_id
        except requests.RequestException as e:
            logger.error(f'Failed to submit session: {e}')
            return None

    # ── Connectivity check ─────────────────────────────────────────────────
    def ping(self) -> bool:
        """Return True if the server is reachable."""
        try:
            r = requests.get(f'{self.base}/login', timeout=self.timeout, verify=self.verify)
            return r.status_code < 500
        except requests.RequestException:
            return False
