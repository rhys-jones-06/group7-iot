# ===========================================================================
# LockIn — pi/main.py
# CM2211 Group 07 — Internet of Things
#
# Integrates threaded YOLO camera/posture detection with the
# Pomodoro session loop and server sync.
#
# Features wired here:
#   F1 — Camera-based desk presence: timer pauses when no person in frame
#   F2 — Phone detection: read from camera thread shared state
#   F3 — Posture detection: read from posture thread shared state
#   F4 — Escalating alerts: LED → buzzer → motor based on distraction duration
#   F5 — LCD countdown: display thread reads shared state and updates LCD
#   F6 — Server sync: submit completed sessions via HTTP client
# ===========================================================================

import logging
import signal
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import config
import client as lockin_client
from detection.camera import start_phone_detection
from detection.posture import start_posture_detection

try:
    import RPi.GPIO as GPIO
    import grovepi
    grovepi.pinMode(config.BUZZER_PIN, "OUTPUT")
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(config.LED_PIN, GPIO.OUT)
    GROVEPI_AVAILABLE = True
except Exception:
    GROVEPI_AVAILABLE = False

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# Shared state — written by detection threads and session loop,
# read by posture thread and LCD display thread
state_lock = threading.Lock()
shared_state = {
    "running":               True,
    # Detection (written by camera/posture threads — F2, F3)
    "phone_detected":        False,
    "phone_confidence":      0.0,
    "latest_frame":          None,
    "person_head_y":         None,
    "posture_status":        "starting",
    "head_drop_pct":         0.0,
    # Session (written by run_session, read by LCD thread — F5)
    "session_state":         "idle",   # idle | focus | paused | break
    "session_remaining_secs": 0,
    "session_distractions":  0,
    "is_distracted":         False,
}

POLL_INTERVAL_SECS    = 1.0
NO_PERSON_THRESHOLD   = 10.0   # seconds before pausing (F1)
LIGHT_SENSOR_PIN      = 2      # Grove light sensor analog pin
DARK_THRESHOLD        = 10     # below this lux value → suppress buzzer (F4)

# F4 escalation ladder: (min continuous distraction seconds, alert level)
ESCALATION = [(0, 1), (10, 2), (20, 3)]


def _handle_shutdown(sig, frame):
    with state_lock:
        shared_state["running"] = False

signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)


# ── Hardware helpers ───────────────────────────────────────────────────────────

def _is_dark() -> bool:
    """F4: read ambient light to decide whether to suppress buzzer."""
    if not GROVEPI_AVAILABLE:
        return False
    try:
        return grovepi.analogRead(LIGHT_SENSOR_PIN) <= DARK_THRESHOLD
    except Exception:
        return False


def _vibrate_motor() -> None:
    """F4 level 3: servo motor vibration."""
    try:
        pwm = GPIO.PWM(18, 50)
        pwm.start(7.5)
        for _ in range(20):
            pwm.ChangeDutyCycle(8.0)
            time.sleep(0.006)
            pwm.ChangeDutyCycle(7.0)
            time.sleep(0.006)
        pwm.stop()
    except Exception as e:
        logger.warning(f'Motor error: {e}')


def _fire_alert(level: int, alert_type: str) -> None:
    """
    F4 escalating alert system:
      Level 1 (0–10s):  LED flash only
      Level 2 (10–20s): LED + buzzer (suppressed if room is dark)
      Level 3 (20s+):   LED + buzzer + motor vibration
    """
    dark = _is_dark()
    logger.info(f'  Alert level {level} (dark={dark})')
    if not GROVEPI_AVAILABLE:
        return
    try:
        # Level 1+: LED flash
        GPIO.output(config.LED_PIN, GPIO.HIGH)
        time.sleep(0.15)
        GPIO.output(config.LED_PIN, GPIO.LOW)

        # Level 2+: buzzer (skip if dark — don't disturb others)
        if level >= 2 and not dark and alert_type in ('audio', 'both'):
            grovepi.analogWrite(config.BUZZER_PIN, 1)
            time.sleep(0.4)
            grovepi.analogWrite(config.BUZZER_PIN, 0)

        # Level 3: motor vibration
        if level >= 3:
            _vibrate_motor()
    except Exception as e:
        logger.warning(f'Alert hardware error: {e}')


# ── Calibration wait ───────────────────────────────────────────────────────────

def _wait_for_calibration() -> None:
    logger.info('Waiting for posture calibration — sit upright...')
    while True:
        with state_lock:
            status  = shared_state.get('posture_status', 'starting')
            running = shared_state.get('running', True)
        if not running:
            return
        if status not in ('starting', 'calibrating'):
            break
        time.sleep(1.0)
    logger.info('Posture calibrated — ready.')


# ── Pomodoro session ───────────────────────────────────────────────────────────

def run_session(
    settings: Dict[str, Any],
    client: lockin_client.LockInClient,
    session_number: int,
) -> None:
    duration_secs   = settings['session_duration_mins'] * 60
    phone_enabled   = settings.get('phone_detection_enabled', True)
    posture_enabled = settings.get('posture_detection_enabled', True)
    alert_type      = settings.get('alert_type', 'both')

    logger.info(f'─── Session {session_number} starting ({settings["session_duration_mins"]} min) ───')

    distractions: List[Dict[str, Any]] = []

    # F1: camera-based presence — elapsed only ticks while person is in frame
    elapsed        = 0.0
    no_person_secs = 0.0
    paused         = False

    # F4: track continuous distraction period for escalation
    distraction_since: Optional[float] = None
    last_fired_level                   = 0

    with state_lock:
        shared_state['session_state']          = 'focus'
        shared_state['session_remaining_secs'] = int(duration_secs)
        shared_state['session_distractions']   = 0
        shared_state['is_distracted']          = False

    while elapsed < duration_secs:
        time.sleep(POLL_INTERVAL_SECS)

        with state_lock:
            if not shared_state.get('running', True):
                break
            phone_detected   = shared_state['phone_detected']
            phone_confidence = shared_state['phone_confidence']
            posture_status   = shared_state['posture_status']

        # ── F1: desk presence ──────────────────────────────────────────────
        if posture_status == 'no person':
            no_person_secs += POLL_INTERVAL_SECS
            if no_person_secs >= NO_PERSON_THRESHOLD and not paused:
                paused = True
                with state_lock:
                    shared_state['session_state'] = 'paused'
                logger.info('  No person detected — session paused')
        else:
            if paused:
                paused = False
                with state_lock:
                    shared_state['session_state'] = 'focus'
                logger.info('  Person returned — session resumed')
            no_person_secs = 0.0

        if paused:
            continue

        elapsed   += POLL_INTERVAL_SECS
        remaining  = max(0.0, duration_secs - elapsed)

        if int(elapsed) % 60 == 0 and int(elapsed) > 0:
            logger.info(f'  {int(remaining // 60)}m remaining')

        # ── F2 + F3: distraction detection ────────────────────────────────
        now           = time.time()
        is_distracted = (phone_enabled and phone_detected) or \
                        (posture_enabled and posture_status == 'bad')

        if is_distracted:
            if distraction_since is None:
                # New distraction period starts — record event(s)
                distraction_since = now
                if phone_enabled and phone_detected:
                    distractions.append({
                        'timestamp':  datetime.utcnow().isoformat(),
                        'type':       'phone',
                        'confidence': phone_confidence,
                    })
                    logger.info(f'  Phone detected (confidence={phone_confidence:.2f})')
                if posture_enabled and posture_status == 'bad':
                    distractions.append({
                        'timestamp':  datetime.utcnow().isoformat(),
                        'type':       'posture',
                        'confidence': None,
                    })
                    logger.info('  Bad posture detected')

            # F4: escalate alert level based on continuous duration
            duration  = now - distraction_since
            new_level = max(lvl for t, lvl in ESCALATION if duration >= t)
            if new_level > last_fired_level:
                _fire_alert(new_level, alert_type)
                last_fired_level = new_level
        else:
            distraction_since = None
            last_fired_level  = 0

        with state_lock:
            shared_state['session_remaining_secs'] = int(remaining)
            shared_state['session_distractions']   = len(distractions)
            shared_state['is_distracted']          = is_distracted

    # ── Session complete ───────────────────────────────────────────────────
    actual_duration   = elapsed / 60
    distraction_count = len(distractions)
    penalty_per       = 100 / max(settings['session_duration_mins'], 1)
    focus_score       = max(0.0, 100.0 - distraction_count * penalty_per)

    logger.info(
        f'Session complete — {round(actual_duration, 1)} min, '
        f'{distraction_count} distractions, score={round(focus_score, 1)}'
    )

    with state_lock:
        shared_state['session_state']  = 'idle'
        shared_state['is_distracted']  = False

    client.submit_session(
        duration_mins=actual_duration,
        distraction_count=distraction_count,
        focus_score=focus_score,
        streak_days=0,
        distractions=distractions,
    )


def run_break(duration_mins: int, label: str) -> None:
    logger.info(f'Break: {label} ({duration_mins} min)')
    end_time = time.time() + duration_mins * 60

    with state_lock:
        shared_state['session_state']          = 'break'
        shared_state['session_remaining_secs'] = duration_mins * 60
        shared_state['session_distractions']   = 0
        shared_state['is_distracted']          = False

    while time.time() < end_time:
        with state_lock:
            if not shared_state.get('running', True):
                return
            shared_state['session_remaining_secs'] = int(end_time - time.time())
        time.sleep(5.0)

    with state_lock:
        shared_state['session_state'] = 'idle'


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print('=' * 65)
    print('  LockIn — Pomodoro + Detection Mode')
    print('  F2: Phone  |  F3: Posture  |  F4: Escalating alerts')
    print('  Sit properly and wait ~8 seconds (posture calibration)')
    print('=' * 65)
    print()

    # F5: LCD display thread
    try:
        from feedback.display import start_lcd_display
        lcd_thread = threading.Thread(
            target=start_lcd_display,
            args=(shared_state, state_lock),
            daemon=True,
        )
        lcd_thread.start()
        logger.info('LCD display thread started (F5).')
    except Exception as e:
        logger.warning(f'LCD unavailable: {e}')

    # F2: camera thread
    camera_thread = threading.Thread(
        target=start_phone_detection,
        args=(shared_state, state_lock),
        daemon=True,
    )
    # F3: posture thread
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

    # F6: connect to server
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
