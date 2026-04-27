# Light sensor in A2, light/button in D8
# Turn the light on when the light sensor also detects light.

import time

import grovepi

PIN_LIGHT_SENSOR = 2
PIN_LIGHT_BUTTON = 8

grovepi.pinMode(PIN_LIGHT_SENSOR,"INPUT")
grovepi.pinMode(PIN_LIGHT_BUTTON,"OUTPUT")

# Turn on LED once sensor exceeds threshold value.
# Value can go up to 1023, but seems to cap at 827.
THRESHOLD = 10


def start_light_monitoring(state: GlobalState, state_lock: threading.Lock) -> None:
    logger.info("Starting light sensor monitoring thread")

    time.sleep(1)
    grovepi.pinMode(LIGHT_PIN, "INPUT")

    while True:
        sensor_value = grovepi.analogRead(LIGHT_PIN)

        with state_lock:
            if not state.running:
                break

            state.low_light = sensor_value < LIGHT_THRESHOLD

        time.sleep(2.5)
