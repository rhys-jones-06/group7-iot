# GrovePI+ has PWM ports but they are locked to a specific frequency via firmware incompatible with a servo.
# This would require custom firmware, which is quite risky and time-consuming to test, and may cause side-effects.
# Instead, jumper cables can be used from the servo to the GPIO pins.
# This uses 5V, ground, and GPIO 18 (pin 12, 6th pin down on the right, from the top right).
# This allows for custom 50Hz PWM control of the servo, as 1000Hz or so does not produce output.

# 1: 5V (red)
# 2: Ground (black)
# 3: Signal (orange)

# o o
# o 1
# o 2
# o o
# o o
# o 3

import logging
import threading
import time

import RPi.GPIO as GPIO
import grovepi

from config import BUZZER_PIN, BUZZER_VOLUME, LED_PIN, MOTOR_PIN
from hardware import i2c_lock
from state import GlobalState

logger = logging.getLogger(__name__)

GPIO.setmode(GPIO.BCM)
GPIO.setup(MOTOR_PIN, GPIO.OUT)

try:
    with i2c_lock:
        grovepi.pinMode(BUZZER_PIN, "OUTPUT")
except Exception as e:
    logger.warning("Buzzer init failed: %s", e)

_pwm = None


def _get_pwm():
    global _pwm
    if _pwm is None:
        _pwm = GPIO.PWM(MOTOR_PIN, 50)
        _pwm.start(7.5)
    return _pwm


def set_angle(angle: float) -> None:
    duty = 2 + (angle / 18)
    _get_pwm().ChangeDutyCycle(duty)
    time.sleep(0.006)


def vibrate(center: float = 90, amplitude: float = 3, cycles: int = 15) -> None:
    """Vibrate the servo around a centre angle, by a given amplitude, for a number of cycles."""
    try:
        for _ in range(cycles):
            set_angle(center + amplitude)
            set_angle(center - amplitude)
    except Exception as e:
        logger.warning("Vibrate failed: %s", e)


def _grovepi_write(fn, *args):
    """Call a grovepi function with the i2c lock, swallowing errors to prevent freezes."""
    try:
        with i2c_lock:
            fn(*args)
    except Exception as e:
        logger.warning("GrovePi call failed: %s", e)


# level 1: 0–10s  - LED flash
# level 2: 10–20s - Buzzer (skipped in low-light — LED only)
# level 3: 20s+   - Motor vibration
def start_alert_feedback(state: GlobalState, lock: threading.RLock) -> None:
    try:
        with i2c_lock:
            grovepi.pinMode(LED_PIN, "OUTPUT")
    except Exception as e:
        logger.warning("LED init failed: %s", e)

    while True:
        with lock:
            if not state.running:
                break
            low_light           = state.low_light
            phone_detected      = state.phone_detected
            distraction_seconds = state.distraction_seconds

        if phone_detected:
            if distraction_seconds > 20:
                # F4: level 3: motor vibration
                vibrate()
            elif distraction_seconds > 10:
                # F4: level 2: louder buzzer
                if not low_light:
                    _grovepi_write(grovepi.analogWrite, BUZZER_PIN, min(BUZZER_VOLUME * 2, 255))
                    time.sleep(0.5)
                    _grovepi_write(grovepi.analogWrite, BUZZER_PIN, 0)
            else:
                # F4: level 1: buzzer beep
                if not low_light:
                    _grovepi_write(grovepi.analogWrite, BUZZER_PIN, BUZZER_VOLUME)
                    time.sleep(0.3)
                    _grovepi_write(grovepi.analogWrite, BUZZER_PIN, 0)

        time.sleep(0.5)

    if _pwm is not None:
        _pwm.stop()
    GPIO.cleanup()