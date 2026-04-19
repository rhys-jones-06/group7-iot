# Light sensor in A2, light/button in D8
# Turn the light on when the light sensor also detects light.

import logging
import threading
import time
import grovepi

from pi.state import GlobalState
from config import LIGHT_PIN, LIGHT_THRESHOLD

logger = logging.getLogger(__name__)


def start_light_monitoring(state: GlobalState, state_lock: threading.Lock) -> None:
    grovepi.pinMode(LIGHT_PIN, "INPUT")

    logger.info("Starting light sensor monitoring thread")

    while True:
        sensor_value = grovepi.analogRead(LIGHT_PIN)

        with state_lock:
            state.low_light = sensor_value < LIGHT_THRESHOLD

        print(f"{sensor_value}")
        time.sleep(0.5)
