from __future__ import annotations

import logging
import signal
import threading
import time
from types import FrameType
from typing import Callable

import config as _config
from client import LockInClient
from config import LOG_LEVEL
from detection.camera import start_phone_detection
from detection.posture import start_posture_detection
from feedback.alert import start_alert_feedback
from feedback.display import menu_handling_thread
from sensors.light import start_light_monitoring
from session.timer import PomodoroState, timer_thread
from state import GlobalState

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

state_lock = threading.RLock()


class MainRunner:
    def __init__(self, state: GlobalState) -> None:
        self.state = state
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
        self.display_thread = threading.Thread(
            target=menu_handling_thread,
            args=(state, state_lock),
            daemon=True,
        )
        self.timer_thread = threading.Thread(
            target=timer_thread,
            args=(state, state_lock),
            daemon=True,
        )

    def splash_screen(self) -> None:
        print()
        print("=" * 65)
        print("  LockIn — Focus Monitor")
        print("  F2: Phone  |  F3: Posture  |  F4: Alerts  |  F5: LCD")
        print("=" * 65)
        print("  Sit properly and wait ~8 seconds (posture calibration)")
        print("  Use joystick to navigate LCD menu, click to start timer")
        print("  Ctrl+C to stop.")
        print("=" * 65)
        print()

    def start(self) -> None:
        logger.info("Starting camera thread (F2)...")
        self.camera_thread.start()
        logger.info("Starting posture thread (F3)...")
        self.posture_thread.start()
        logger.info("Starting alert thread (F4)...")
        self.alert_thread.start()
        logger.info("Starting display thread (F5)...")
        self.display_thread.start()
        logger.info("Starting light thread...")
        self.light_thread.start()
        logger.info("Starting timer thread...")
        self.timer_thread.start()
        self.splash_screen()
        logger.info("Running.")

    def stop(self) -> None:
        with state_lock:
            self.state.running = False
        logger.info("Stopping...")

        threads = [
            self.camera_thread,
            self.posture_thread,
            self.light_thread,
            self.alert_thread,
            self.display_thread,
            self.timer_thread,
        ]

        deadline = time.time() + 5.0
        for thread in threads:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)

        alive = [t.name for t in threads if t.is_alive()]
        if alive:
            logger.warning("Shutdown timeout; still running: %s", ", ".join(alive))

        logger.info("Done.")

    def loop(self) -> None:
        while True:
            with state_lock:
                if not self.state.running:
                    break
                phone   = self.state.phone_detected
                conf    = self.state.phone_confidence
                posture = self.state.posture_status
                drop    = self.state.head_drop_pct

            if self.state.timer.state != PomodoroState.RUNNING:
                time.sleep(1.0)
                continue

            is_distracted = phone

            if is_distracted:
                if self.state.distraction_start is None:
                    with state_lock:
                        self.state.distraction_start = time.time()
                        self.state.session_distraction_count += 1
                with state_lock:
                    dist_secs = time.time() - self.state.distraction_start
                    self.state.distraction_seconds = dist_secs
            else:
                with state_lock:
                    self.state.distraction_start = None
                    self.state.distraction_seconds = 0.0
                dist_secs = 0.0

            p = "PHONE ({:.0%})".format(conf) if phone else "no phone"

            if posture == "calibrating":
                s = "calibrating..."
            elif posture == "good":
                s = "GOOD (drop {:.0%})".format(drop) if drop > 0.01 else "GOOD"
            elif posture == "bad":
                s = "SLOUCHING ({:.0%} drop)".format(drop)
            elif posture == "no person":
                s = "no person"
            else:
                s = posture

            if is_distracted:
                o = "!! DISTRACTED {:.0f}s !!".format(dist_secs)
            elif posture == "bad":
                o = "!! SIT UP !!"
            else:
                o = "focused"

            l = "t" if self.state.low_light else "f"
            print(" Light: {} | Phone: {:18s} | Posture: {:22s} | {}".format(l, p, s, o))

            time.sleep(1.0)


def _handle_shutdown(state: GlobalState) -> Callable[[int, FrameType | None], None]:
    def inner(_sig: int, _frame: FrameType | None) -> None:
        with state_lock:
            state.running = False
    return inner


def main() -> None:
    cfg = _config.load()
    client = LockInClient(cfg['server_url'], cfg['api_key'])

    logger.info("Connecting to server %s ...", cfg['server_url'])
    if client.ping():
        logger.info("Server reachable")
        settings = client.get_settings()
    else:
        logger.warning("Server unreachable — using local defaults")
        settings = {}

    state = GlobalState(lock=state_lock)
    state.client = client

    if settings.get('session_duration_mins'):
        state.timer.config.focus_duration = int(settings['session_duration_mins'])
    if settings.get('short_break_mins'):
        state.timer.config.break_duration = int(settings['short_break_mins'])

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
