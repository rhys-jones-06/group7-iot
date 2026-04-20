"""
LockIn Pi — Main Session Loop
CM2211 Group 07 — Internet of Things

Flow:
  1. Read /boot/lockin.conf  →  get server URL + API key
  2. Fetch settings from server (Pomodoro durations, detection toggles, etc.)
  3. Run Pomodoro sessions indefinitely:
       - Start timer
       - Detect phone / posture at regular intervals
       - Submit completed session to server
       - Break, then repeat

Detection stubs (detection/phone.py, detection/posture.py) are called here;
replace the stub return values with your actual model inference.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import config
import client as lockin_client

# ── Detection imports ────────────────────────────────────────────────────────
# These modules should expose:
#   phone.detect(frame, sensitivity) -> Optional[float]   (confidence, or None)
#   posture.detect(frame)            -> bool               (True = bad posture)
try:
    from detection import phone as phone_det
    from detection import posture as posture_det
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

DETECTION_INTERVAL_SECS = 2   # how often to run detection during a session


# ── Camera helper ─────────────────────────────────────────────────────────────

def _get_frame():
    """Capture a single frame from the Pi camera. Returns None if unavailable."""
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        ok, frame = cap.read()
        cap.release()
        return frame if ok else None
    except Exception:
        return None


# ── Alert helper ──────────────────────────────────────────────────────────────

def _alert(alert_type: str, message: str) -> None:
    """Issue an alert (LED flash, buzzer, or both)."""
    logger.info(f'ALERT [{alert_type}]: {message}')
    # TODO: wire up GPIO for LED / buzzer based on alert_type


# ── Pomodoro session ──────────────────────────────────────────────────────────

def run_session(
    settings: Dict[str, Any],
    client: lockin_client.LockInClient,
    session_number: int,
) -> None:
    duration_secs  = settings['session_duration_mins'] * 60
    sensitivity    = settings.get('phone_sensitivity', 0.7)
    phone_enabled  = settings.get('phone_detection_enabled', True)
    posture_enabled = settings.get('posture_detection_enabled', True)
    alert_type     = settings.get('alert_type', 'both')
    cooldown_secs  = settings.get('alert_cooldown_secs', 30)

    logger.info(f'─── Session {session_number} starting ({settings["session_duration_mins"]} min) ───')

    distractions: List[Dict[str, Any]] = []
    last_alert_time: float = 0.0
    start_time = time.time()
    elapsed = 0.0

    while elapsed < duration_secs:
        time.sleep(DETECTION_INTERVAL_SECS)
        elapsed = time.time() - start_time
        remaining = max(0, duration_secs - elapsed)

        if int(elapsed) % 60 == 0 and int(elapsed) > 0:
            logger.info(f'  {int(remaining // 60)}m remaining')

        if not CAMERA_AVAILABLE:
            continue

        frame = _get_frame()
        if frame is None:
            continue

        now = time.time()
        can_alert = (now - last_alert_time) >= cooldown_secs

        # Phone detection
        if phone_enabled:
            confidence: Optional[float] = phone_det.detect(frame, sensitivity)
            if confidence is not None:
                ts = datetime.utcnow().isoformat()
                distractions.append({'timestamp': ts, 'type': 'phone', 'confidence': confidence})
                logger.info(f'  Phone detected (confidence={confidence:.2f})')
                if can_alert:
                    _alert(alert_type, 'Put your phone down!')
                    last_alert_time = now

        # Posture detection
        if posture_enabled:
            bad_posture: bool = posture_det.detect(frame)
            if bad_posture:
                ts = datetime.utcnow().isoformat()
                distractions.append({'timestamp': ts, 'type': 'posture', 'confidence': None})
                logger.info('  Bad posture detected')
                if can_alert:
                    _alert(alert_type, 'Check your posture!')
                    last_alert_time = now

    # ── Session complete ──────────────────────────────────────────────────
    actual_duration = (time.time() - start_time) / 60
    distraction_count = len(distractions)

    # Focus score: 100 minus a penalty per distraction, scaled by session length
    penalty_per = 100 / max(settings['session_duration_mins'], 1)
    focus_score = max(0.0, 100.0 - distraction_count * penalty_per)

    logger.info(
        f'Session complete — {round(actual_duration, 1)} min, '
        f'{distraction_count} distractions, score={round(focus_score, 1)}'
    )

    client.submit_session(
        duration_mins=actual_duration,
        distraction_count=distraction_count,
        focus_score=focus_score,
        streak_days=0,          # server computes authoritative streak
        distractions=distractions,
    )


def run_break(duration_mins: int, label: str) -> None:
    logger.info(f'Break: {label} ({duration_mins} min)')
    time.sleep(duration_mins * 60)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = config.load()
    logger.info(f'Connecting to {cfg["server_url"]}')

    client = lockin_client.LockInClient(cfg['server_url'], cfg['api_key'])

    # Wait for network / server to be reachable
    retries = 0
    while not client.ping():
        wait = min(30, 5 * (retries + 1))
        logger.warning(f'Server unreachable, retrying in {wait}s…')
        time.sleep(wait)
        retries += 1

    settings = client.get_settings()
    logger.info('Settings loaded. Starting LockIn session loop.')

    session_number = 1
    while True:
        run_session(settings, client, session_number)

        # Refresh settings after each session (user may have changed them)
        settings = client.get_settings()

        sessions_before_long = settings.get('sessions_before_long_break', 4)
        if session_number % sessions_before_long == 0:
            run_break(settings['long_break_mins'], 'long break')
        else:
            run_break(settings['short_break_mins'], 'short break')

        session_number += 1


if __name__ == '__main__':
    main()
