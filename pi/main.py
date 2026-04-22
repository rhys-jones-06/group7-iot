# ===========================================================================
# LockIn — pi/main.py
# CM2211 Group 07 — Internet of Things
#
# Integrates threaded YOLO camera/posture detection with the
# Pomodoro session loop and server sync.
#
# Flow:
#   1. Start camera + posture detection threads (continuous, background)
#   2. Read /boot/lockin.conf → connect to server
#   3. Wait for posture calibration
#   4. Run Pomodoro sessions indefinitely:
#        - Read phone/posture state from detection threads
#        - Issue hardware alerts (buzzer) on distraction
#        - Submit completed session to server
#        - Break, then repeat
# ===========================================================================

import logging
import signal
import threading
import time
from datetime import datetime
from typing import Any, Dict, List

import config
import client as lockin_client
from detection.camera import start_phone_detection
from detection.posture import start_posture_detection

try:
    import grovepi
    grovepi.pinMode(config.BUZZER_PIN, "OUTPUT")
    GROVEPI_AVAILABLE = True
except Exception:
    GROVEPI_AVAILABLE = False

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# Shared state — written by detection threads, read by session loop
state_lock = threading.Lock()
shared_state = {
    "running": True,
    "phone_detected": False,
    "phone_confidence": 0.0,
    "latest_frame": None,
    "person_head_y": None,
    "posture_status": "starting",
    "head_drop_pct": 0.0,
}

POLL_INTERVAL_SECS = 1.0


def _handle_shutdown(sig, frame):
    with state_lock:
        shared_state["running"] = False

signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)


def _alert(alert_type: str, message: str) -> None:
    """Trigger buzzer alert based on the user's configured alert type."""
    logger.info(f'ALERT [{alert_type}]: {message}')
    if not GROVEPI_AVAILABLE:
        return
    try:
        if alert_type in ('audio', 'both'):
            grovepi.analogWrite(config.BUZZER_PIN, 1)
            time.sleep(0.5)
            grovepi.analogWrite(config.BUZZER_PIN, 0)
    except Exception as e:
        logger.warning(f'Alert hardware error: {e}')


def _wait_for_calibration() -> None:
    """Block until the posture thread finishes calibrating."""
    logger.info('Waiting for posture calibration — sit upright...')
    while True:
        with state_lock:
            status = shared_state.get('posture_status', 'starting')
            running = shared_state.get('running', True)
        if not running:
            return
        if status not in ('starting', 'calibrating'):
            break
        time.sleep(1.0)
    logger.info('Posture calibrated — ready.')


def run_session(
    settings: Dict[str, Any],
    client: lockin_client.LockInClient,
    session_number: int,
) -> None:
    duration_secs   = settings['session_duration_mins'] * 60
    phone_enabled   = settings.get('phone_detection_enabled', True)
    posture_enabled = settings.get('posture_detection_enabled', True)
    alert_type      = settings.get('alert_type', 'both')
    cooldown_secs   = settings.get('alert_cooldown_secs', 30)

    logger.info(f'─── Session {session_number} starting ({settings["session_duration_mins"]} min) ───')

    distractions: List[Dict[str, Any]] = []
    last_alert_time: float = 0.0
    # F1: elapsed only advances while a person is in frame (camera-based presence)
    elapsed = 0.0
    no_person_secs = 0.0
    paused = False
    NO_PERSON_PAUSE_THRESHOLD = 10.0  # seconds before pausing

    while elapsed < duration_secs:
        time.sleep(POLL_INTERVAL_SECS)

        with state_lock:
            if not shared_state.get('running', True):
                break
            phone_detected   = shared_state['phone_detected']
            phone_confidence = shared_state['phone_confidence']
            posture_status   = shared_state['posture_status']

        # F1: track consecutive seconds with no person detected
        if posture_status == 'no person':
            no_person_secs += POLL_INTERVAL_SECS
            if no_person_secs >= NO_PERSON_PAUSE_THRESHOLD and not paused:
                paused = True
                logger.info('  No person detected — session paused')
        else:
            if paused:
                paused = False
                logger.info('  Person returned — session resumed')
            no_person_secs = 0.0

        if paused:
            continue

        elapsed += POLL_INTERVAL_SECS
        remaining = max(0, duration_secs - elapsed)

        if int(elapsed) % 60 == 0 and int(elapsed) > 0:
            logger.info(f'  {int(remaining // 60)}m remaining')

        now = time.time()
        can_alert = (now - last_alert_time) >= cooldown_secs

        # F2: Phone distraction
        if phone_enabled and phone_detected:
            ts = datetime.utcnow().isoformat()
            distractions.append({'timestamp': ts, 'type': 'phone', 'confidence': phone_confidence})
            logger.info(f'  Phone detected (confidence={phone_confidence:.2f})')
            if can_alert:
                _alert(alert_type, 'Put your phone down!')
                last_alert_time = now

        # F3: Posture distraction
        if posture_enabled and posture_status == 'bad':
            ts = datetime.utcnow().isoformat()
            distractions.append({'timestamp': ts, 'type': 'posture', 'confidence': None})
            logger.info('  Bad posture detected')
            if can_alert:
                _alert(alert_type, 'Check your posture!')
                last_alert_time = now

    actual_duration = elapsed / 60  # excludes time paused away from desk
    distraction_count = len(distractions)
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
        streak_days=0,  # server computes authoritative streak
        distractions=distractions,
    )


def run_break(duration_mins: int, label: str) -> None:
    logger.info(f'Break: {label} ({duration_mins} min)')
    end = time.time() + duration_mins * 60
    while time.time() < end:
        with state_lock:
            if not shared_state.get('running', True):
                return
        time.sleep(5.0)


def main() -> None:
    print()
    print('=' * 65)
    print('  LockIn — Pomodoro + Detection Mode')
    print('  F2: Phone detection  |  F3: Posture detection')
    print('  Sit properly and wait ~8 seconds (posture calibration)')
    print('=' * 65)
    print()

    # Start detection threads
    camera_thread = threading.Thread(
        target=start_phone_detection,
        args=(shared_state, state_lock),
        daemon=True,
    )
    posture_thread = threading.Thread(
        target=start_posture_detection,
        args=(shared_state, state_lock),
        daemon=True,
    )
    logger.info('Starting camera thread (F2)...')
    camera_thread.start()
    time.sleep(2.0)
    logger.info('Starting posture thread (F3)...')
    posture_thread.start()

    # Connect to server
    cfg = config.load()
    logger.info(f'Connecting to {cfg["server_url"]}')
    lockin = lockin_client.LockInClient(cfg['server_url'], cfg['api_key'])

    retries = 0
    while not lockin.ping():
        wait = min(30, 5 * (retries + 1))
        logger.warning(f'Server unreachable, retrying in {wait}s...')
        time.sleep(wait)
        retries += 1

    settings = lockin.get_settings()
    logger.info('Settings loaded.')

    _wait_for_calibration()

    session_number = 1
    while True:
        with state_lock:
            if not shared_state.get('running', True):
                break

        run_session(settings, lockin, session_number)
        settings = lockin.get_settings()

        sessions_before_long = settings.get('sessions_before_long_break', 4)
        if session_number % sessions_before_long == 0:
            run_break(settings['long_break_mins'], 'long break')
        else:
            run_break(settings['short_break_mins'], 'short break')

        session_number += 1

    with state_lock:
        shared_state['running'] = False

    logger.info('Stopping...')
    camera_thread.join(timeout=5.0)
    posture_thread.join(timeout=5.0)
    logger.info('Done.')


if __name__ == '__main__':
    main()
