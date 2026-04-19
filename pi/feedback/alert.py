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

import RPi.GPIO as GPIO
import time
import grovepi

PIN_SERVO = 18
# Can be any of 3, 5, 6, 9 - these are PWM-enabled pins and allow for volume control.
PIN_BUZZER = 5

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_SERVO, GPIO.OUT)

grovepi.pinMode(PIN_BUZZER, "OUTPUT")

pwm = GPIO.PWM(PIN_SERVO, 50)
pwm.start(7.5)  # 7.5 duty cycle is about center position (90 degrees)


def set_angle(angle: float) -> None:
    duty = 2 + (angle / 18)
    pwm.ChangeDutyCycle(duty)
    # very short delay, just enough for servo to respond
    # 0.005 produces no output, so does 0.01, so 0.06 seems the best to produce a good jitter.
    time.sleep(0.006)


def vibrate(center: float = 90, amplitude: float = 3, cycles: int = 50) -> None:
    """Vibrate the servo around a centre angle, by a given amplitude, for a number of cycles."""
    for _ in range(cycles):
        set_angle(center + amplitude)
        set_angle(center - amplitude)


if __name__ == "__main__":
    try:
        while True:
            # Value of 1/255 is much quieter
            grovepi.analogWrite(PIN_BUZZER, 1)
            time.sleep(0.5)
            grovepi.analogWrite(PIN_BUZZER, 0)
            vibrate(center=90, amplitude=3, cycles=30)
    except KeyboardInterrupt:
        pass
    finally:
        pwm.stop()
        GPIO.cleanup()
