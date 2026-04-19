# ===========================================================================
# LockIn — pi/main.py
# CM2211 Group 07
#
# cd ~/lockin/files
# python3 main.py
# ===========================================================================

from __future__ import annotations

import time
import signal
import logging
import threading
from types import FrameType
from typing import Callable

from detection.camera import start_phone_detection
from detection.posture import start_posture_detection
from config import LOG_LEVEL
from feedback.alert import start_alert_feedback
from sensors.light import start_light_monitoring
from state import GlobalState

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    # include % name ALONGSIDE levelname in log fmt
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

state_lock = threading.Lock()


class MainRunner:
    def __init__(self, state: GlobalState) -> None:
        self.state: GlobalState = state

        self.camera_thread = threading.Thread(
            target=start_phone_detection,
            args=(state, state_lock),
            daemon=True,
        )
        self.posture_thread = threading.Thread(
            target=start_posture_detection,
            args=(state, state_lock),
            daemon=True,
        )
        self.light_thread = threading.Thread(
            target=start_light_monitoring,
            args=(state, state_lock),
            daemon=True,
        )
        self.alert_thread = threading.Thread(
            target=start_alert_feedback,
            args=(state, state_lock),
            daemon=True,
        )


    def splash_screen(self) -> None:
        print()
        print("=" * 65)
        print("  LockIn — Local Detection Mode")
        print("  F2: Phone detection  |  F3: Posture detection")
        print("=" * 65)
        print("  1. Sit properly and wait ~8 seconds (posture calibration)")
        print("  2. Hold a phone up to test F2")
        print("  3. Slouch in your chair to test F3")
        print("  Ctrl+C to stop.")
        print("=" * 65)
        print()

    def start(self) -> None:
        logger.info("Starting camera thread (F2)...")
        self.camera_thread.start()
        time.sleep(2.0)
        logger.info("Starting posture thread (F3)...")
        self.posture_thread.start()
        logger.info("Starting light thread (F4)...")
        self.light_thread.start()
        logger.info("Starting alert thread (F4)...")
        self.alert_thread.start()
        self.splash_screen()
        logger.info("Running.\n")

    def stop(self) -> None:
        with state_lock:
            self.state.running = False
        logger.info("Stopping...")
        self.camera_thread.join(timeout=5.0)
        self.posture_thread.join(timeout=5.0)
        self.light_thread.join(timeout=5.0)
        self.alert_thread.join(timeout=5.0)
        logger.info("Done.")

    def loop(self) -> None:
        while True:
            with state_lock:
                if not self.state.running:
                    break
                phone = self.state.phone_detected
                conf = self.state.phone_confidence
                posture = self.state.posture_status
                drop = self.state.head_drop_pct

            # F2: Phone = distracted
            is_distracted = phone

            if is_distracted:
                if self.state.distraction_start is None:
                    with state_lock:
                        self.state.distraction_start = time.time()
                with state_lock:
                    dist_secs = time.time() - self.state.distraction_start
                    self.state.distraction_seconds = dist_secs
            else:
                with state_lock:
                    self.state.distraction_start = None
                    self.state.distraction_seconds = 0.0
                dist_secs = 0.0

            # --- PHONE ---
            if phone:
                p = "PHONE ({:.0%})".format(conf)
            else:
                p = "no phone"

            # --- POSTURE ---
            if posture == "calibrating":
                s = "calibrating..."
            elif posture == "good":
                if drop > 0.01:
                    s = "GOOD (drop {:.0%})".format(drop)
                else:
                    s = "GOOD"
            elif posture == "bad":
                s = "SLOUCHING ({:.0%} drop)".format(drop)
            elif posture == "no person":
                s = "no person"
            else:
                s = posture

            # --- OVERALL ---
            if is_distracted:
                o = "!! DISTRACTED {:.0f}s !!".format(dist_secs)
            elif posture == "bad":
                o = "!! SIT UP — RETURN TO START POSITION !!"
            else:
                o = "focused"

            l = "t" if self.state.low_light else "f"

            print(" Low Light: {} | Phone: {:18s} | Posture: {:22s} | {}".format(l, p, s, o))

            time.sleep(1.0)


def _handle_shutdown(state: GlobalState) -> Callable[[int, FrameType | None], None]:
    def inner(_sig: int, _frame: FrameType | None) -> None:
        with state_lock:
            state.running = False

    return inner


def main():
    state = GlobalState()
    signal.signal(signal.SIGINT, _handle_shutdown(state))
    signal.signal(signal.SIGTERM, _handle_shutdown(state))

    runner = MainRunner(state=state)
    runner.start()

    try:
        runner.loop()
    except KeyboardInterrupt:
        pass

    with state_lock:
        state.running = False

    runner.stop()


if __name__ == "__main__":
    main()
