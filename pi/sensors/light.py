# Light sensor in A2 — reads ambient light to detect low-light conditions.

import logging
import threading
import time

import grovepi

from config import LIGHT_PIN, LIGHT_THRESHOLD
from state import GlobalState

logger = logging.getLogger(__name__)


def start_light_monitoring(state: GlobalState, state_lock: threading.RLock) -> None:
    logger.info("Starting light sensor monitoring thread")

    grovepi.pinMode(LIGHT_PIN, "INPUT")

    while True:
        with state_lock:
            if not state.running:
                break

        sensor_value = grovepi.analogRead(LIGHT_PIN)

        with state_lock:
            state.low_light = sensor_value < LIGHT_THRESHOLD

        time.sleep(2.5)
