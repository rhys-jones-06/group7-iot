# ===========================================================================
# LockIn — pi/feedback/alert.py
# CM2211 Group 07 | F4: Escalating hardware feedback
#
# Triggers (only during an active focus session):
#   1. Phone in view for ≥ DISTRACTION_BUZZ_S → escalating phone alert
#   2. Posture flagged "bad" by detection/posture.py → gentle reminder
#
# Mode is runtime-mutable via state.alert_mode (set by display.py when the
# user toggles the "Alerts" screen on the LCD). Default comes from config.
#
# RULE: one actuator per mode — loud = buzzer only, silent = servo only.
#
#   silent (default — quiet for late-night use)
#       phone tier 1 (2-10 s)  →  gentle servo nudge
#       phone tier 2 (10 s+)   →  firmer/longer servo
#       posture bad            →  brief servo nudge
#
#   loud
#       phone tier 1 (2-10 s)  →  short buzzer pulse
#       phone tier 2 (10 s+)   →  long buzzer pulse
#       posture bad            →  short buzzer pulse
#
# Low-light condition (state.low_light) downgrades any "loud" alert to
# silent for that loop, so the buzzer doesn't disturb anyone nearby.
#
# LED behaviour (Grove D8) — solid on whenever the camera is enabled.
# It is a "camera active" indicator only; never flashes for distractions.
#
# ─── Servo wiring (NOT through GrovePi) ────────────────────────────────────
#   Servo red    → Pi header pin  2  (5 V)
#   Servo black  → Pi header pin  6  (GND)
#   Servo orange → Pi header pin 12  (GPIO 18 / BCM 18)
# ===========================================================================
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import grovepi
import RPi.GPIO as GPIO

from config import (
    BUZZER_PIN, BUZZER_VOLUME, CAMERA_ENABLED,
    DISTRACTION_BUZZ_S, DISTRACTION_SERVO_S,
    LED_PIN, MOTOR_PIN,
)
from session.timer import PomodoroState
from state import GlobalState

logger = logging.getLogger(__name__)

LOOP_IDLE_S = 0.4

# ── module-level servo PWM (lazy init in start_alert_feedback) ───────────────
_pwm: Optional[GPIO.PWM] = None


def _init_motor() -> None:
    """Set up servo PWM on BCM 18 at 50 Hz; idle at duty 0 so it doesn't whine."""
    global _pwm
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(MOTOR_PIN, GPIO.OUT)
    _pwm = GPIO.PWM(MOTOR_PIN, 50)
    _pwm.start(0)


def _set_angle(angle: float) -> None:
    if _pwm is None:
        return
    duty = 2 + (angle / 18.0)
    _pwm.ChangeDutyCycle(duty)
    time.sleep(0.05)             # let the servo physically step
    _pwm.ChangeDutyCycle(0)      # release so it stops drawing current/whining


def _vibrate(centre: float = 90.0, amplitude: float = 6.0, cycles: int = 12) -> None:
    """Oscillate the servo around `centre` to feel like a buzz."""
    for _ in range(cycles):
        _set_angle(centre + amplitude)
        _set_angle(centre - amplitude)


def _set_led(on: bool) -> None:
    try:
        grovepi.digitalWrite(LED_PIN, 1 if on else 0)
    except IOError:
        pass


def _set_buzzer(volume: int) -> None:
    try:
        grovepi.analogWrite(BUZZER_PIN, volume)
    except IOError:
        pass


def _actuators_off() -> None:
    """Silence buzzer and stop servo. Does NOT touch the LED."""
    _set_buzzer(0)
    if _pwm is not None:
        _pwm.ChangeDutyCycle(0)


# ─── thread entry point ─────────────────────────────────────────────────────

def start_alert_feedback(state: GlobalState, state_lock: threading.RLock) -> None:
    try:
        grovepi.pinMode(LED_PIN, "OUTPUT")
        grovepi.pinMode(BUZZER_PIN, "OUTPUT")
        _init_motor()
    except Exception:
        logger.exception("Alert hardware init failed — feedback thread disabled")
        return

    logger.info("Alerts ready (LED D%d, buzzer D%d, servo BCM%d)",
                LED_PIN, BUZZER_PIN, MOTOR_PIN)

    _set_led(CAMERA_ENABLED)

    try:
        while True:
            with state_lock:
                if not state.running:
                    break
                low_light       = state.low_light
                phone_detected  = state.phone_detected
                dist_secs       = state.distraction_seconds
                posture_status  = state.posture_status
                alert_mode      = state.alert_mode
                timer_state     = state.timer.state if state.timer else None

            # Refresh LED every loop so a transient I²C glitch can't strand it off.
            _set_led(CAMERA_ENABLED)

            # ── alerts only fire during an active focus session ─────────────
            if timer_state != PomodoroState.RUNNING:
                _actuators_off()
                time.sleep(LOOP_IDLE_S)
                continue

            # In low light, silently downgrade loud → silent for this loop.
            effective_mode = "silent" if low_light else alert_mode

            phone_active   = phone_detected and dist_secs >= DISTRACTION_BUZZ_S
            posture_active = (posture_status == "bad")

            if phone_active:
                _phone_alert(dist_secs, effective_mode)
            elif posture_active:
                _posture_alert(effective_mode)
            else:
                _actuators_off()
                time.sleep(LOOP_IDLE_S)

    except Exception:
        logger.exception("Alert thread crashed")
    finally:
        _actuators_off()
        _set_led(False)
        if _pwm is not None:
            try:
                _pwm.stop()
            except Exception:
                pass
        try:
            GPIO.cleanup(MOTOR_PIN)
        except Exception:
            pass
        logger.info("Alerts stopped")


# ─── trigger handlers ───────────────────────────────────────────────────────

def _phone_alert(dist_secs: float, mode: str) -> None:
    """Tier 1 (2-10 s) and Tier 2 (10 s+) phone feedback.
    One actuator per mode — loud = buzzer only, silent = servo only."""
    high_tier = dist_secs >= DISTRACTION_SERVO_S

    if mode == "loud":
        # Buzzer only. Tier 2 = longer pulse so you can tell it's escalated.
        if high_tier:
            _set_buzzer(BUZZER_VOLUME)
            time.sleep(0.50)
            _set_buzzer(0)
            time.sleep(0.15)
        else:
            _set_buzzer(BUZZER_VOLUME)
            time.sleep(0.12)
            _set_buzzer(0)
            time.sleep(0.18)
    else:
        # silent: servo only.
        _set_buzzer(0)
        if high_tier:
            _vibrate(cycles=18, amplitude=8.0)   # firmer, longer
            time.sleep(0.2)
        else:
            _vibrate(cycles=8, amplitude=5.0)    # gentler nudge
            time.sleep(0.4)


def _posture_alert(mode: str) -> None:
    """Brief reminder while posture is flagged bad — fires every loop.
    One actuator per mode — loud = buzzer only, silent = servo only."""
    if mode == "loud":
        _set_buzzer(BUZZER_VOLUME)
        time.sleep(0.08)
        _set_buzzer(0)
        time.sleep(0.4)
    else:
        _set_buzzer(0)
        _vibrate(cycles=6, amplitude=4.0)
        time.sleep(LOOP_IDLE_S)
