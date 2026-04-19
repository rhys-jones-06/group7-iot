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

from config import BUZZER_PIN, LED_PIN, MOTOR_PIN, BUZZER_VOLUME
from state import GlobalState

logger = logging.getLogger(__name__)

GPIO.setmode(GPIO.BCM)
GPIO.setup(MOTOR_PIN, GPIO.OUT)

grovepi.pinMode(BUZZER_PIN, "OUTPUT")

pwm = GPIO.PWM(MOTOR_PIN, 50)


def set_angle(angle: float) -> None:
    duty = 2 + (angle / 18)
    pwm.ChangeDutyCycle(duty)
    # very short delay, just enough for servo to respond
    # 0.005 produces no output, so does 0.01, so 0.06 seems the best to produce a good jitter.
    time.sleep(0.006)


def vibrate(center: float = 90, amplitude: float = 3, cycles: int = 50) -> None:
    """Vibrate the servo around a centre angle, by a given amplitude, for a number of cycles."""

    # 7.5 duty cycle is about center position (90 degrees)
    pwm.start(7.5)
    for _ in range(cycles):
        set_angle(center + amplitude)
        set_angle(center - amplitude)
    pwm.stop()


# level 1: 0–10s  - LED flash
# level 2: 10–20s - Buzzer (skipped in low-light — LED only)
# level 3: 20s+   - Motor vibration
def start_alert_feedback(state: GlobalState, lock: threading.Lock) -> None:
    grovepi.pinMode(LED_PIN, "OUTPUT")

    while True:
        with lock:
            if not state.running:
                break
            low_light = state.low_light
            phone_detected = state.phone_detected
            distraction_seconds = state.distraction_seconds

        if phone_detected:
            if distraction_seconds > 20:
                logger.info("Distraction detected for %.1f seconds — activating motor vibration", distraction_seconds)
                # F4: level 3: motor vibration
                vibrate()
            elif distraction_seconds > 10:
                # F4: level 2: buzzer (skipped in low-light — LED only)
                if not low_light:
                    grovepi.analogWrite(BUZZER_PIN, BUZZER_VOLUME)
                    time.sleep(0.5)
                    grovepi.analogWrite(BUZZER_PIN, 0)
            else:
                # F4: level 1: LED flash
                grovepi.digitalWrite(LED_PIN, 1)
                time.sleep(0.5)
                grovepi.digitalWrite(LED_PIN, 0)
        time.sleep(0.5)
