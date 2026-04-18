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

from detection.camera import start_phone_detection
from detection.posture import start_posture_detection
from config import LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

state_lock = threading.Lock()
shared_state = {
    "running": True,
    "phone_detected": False,
    "phone_confidence": 0.0,
    "latest_frame": None,
    "person_head_y": None,
    "posture_status": "starting",
    "head_drop_pct": 0.0,
    "distraction_start": None,
    "distraction_seconds": 0.0,
}


class MainRunner:
    def __init__(self) -> None:
        self.camera_thread = threading.Thread(
            target=start_phone_detection,
            args=(shared_state, state_lock),
            daemon=True,
        )
        self.posture_thread = threading.Thread(
            target=start_posture_detection,
            args=(shared_state, state_lock),
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
        logger.info("Running.\n")

    def stop(self) -> None:
        with state_lock:
            shared_state["running"] = False
        logger.info("Stopping...")
        self.camera_thread.join(timeout=5.0)
        self.posture_thread.join(timeout=5.0)
        logger.info("Done.")

    def loop(self) -> None:
        while True:
            with state_lock:
                if not shared_state["running"]:
                    break
                phone = shared_state["phone_detected"]
                conf = shared_state["phone_confidence"]
                posture = shared_state["posture_status"]
                drop = shared_state["head_drop_pct"]

            # F2: Phone = distracted
            is_distracted = phone

            if is_distracted:
                if shared_state["distraction_start"] is None:
                    with state_lock:
                        shared_state["distraction_start"] = time.time()
                with state_lock:
                    dist_secs = time.time() - shared_state["distraction_start"]
                    shared_state["distraction_seconds"] = dist_secs
            else:
                with state_lock:
                    shared_state["distraction_start"] = None
                    shared_state["distraction_seconds"] = 0.0
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

            print("  Phone: {:18s} | Posture: {:22s} | {}".format(p, s, o))

            time.sleep(1.0)

def _handle_shutdown(_sig: int, _frame: FrameType | None) -> None:
    with state_lock:
        shared_state["running"] = False


def main():
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    runner = MainRunner()
    runner.start()

    try:
        runner.loop()
    except KeyboardInterrupt:
        pass

    with state_lock:
        shared_state["running"] = False

    runner.stop()


if __name__ == "__main__":
    main()
