# ===========================================================================
# LockIn — pi/detection/posture.py
# CM2211 Group 07 | Feature F3: Posture / Slouch Detection
#
# HOW IT WORKS:
#   YOLO already detects you as a "person" every frame for F2.
#   The top of that bounding box = the top of your head.
#
#   1. CALIBRATION: Sit properly for a few seconds. The system learns
#      where the top of your head normally is.
#   2. MONITORING: If the top of your head drops (you slouch),
#      your head position sinks in the frame.
#      If it drops more than the threshold for 5+ seconds → bad posture.
#   3. When you sit back up, the drop goes away and it shows "GOOD".
# ===========================================================================

import time
import logging
import threading

from config import (
    POSTURE_ENABLED, FACE_DROP_THRESHOLD,
    POSTURE_SUSTAINED_S, FACE_BASELINE_FRAMES,
    CAMERA_FPS_CAP,
)
from state import GlobalState

logger = logging.getLogger(__name__)


def start_posture_detection(state: GlobalState, state_lock: threading.RLock) -> None:
    if not POSTURE_ENABLED:
        return

    logger.info("Using YOLO person detection for posture tracking")

    baseline_readings = []
    baseline_y = None
    slouching_since = None

    check_interval = 1.0 / CAMERA_FPS_CAP

    try:
        while True:
            with state_lock:
                if not state.running:
                    break
                head_y = state.person_head_y

            if head_y is None:
                slouching_since = None
                with state_lock:
                    state.posture_status = "no person"
                    state.head_drop_pct  = 0.0
                time.sleep(check_interval)
                continue

            now = time.time()

            if len(baseline_readings) < FACE_BASELINE_FRAMES:
                baseline_readings.append(head_y)

                if len(baseline_readings) == FACE_BASELINE_FRAMES:
                    baseline_y = sum(baseline_readings) / len(baseline_readings)
                    logger.info("Baseline calibrated: head top at %.1f%% of frame", baseline_y * 100)
                    logger.info("Sit like this = good posture. Slouching will be detected.")

                with state_lock:
                    state.posture_status = "calibrating"
                    state.head_drop_pct  = 0.0

            else:
                drop = head_y - baseline_y

                if drop > FACE_DROP_THRESHOLD:
                    if slouching_since is None:
                        slouching_since = now

                    duration = now - slouching_since

                    if duration >= POSTURE_SUSTAINED_S:
                        with state_lock:
                            state.posture_status = "bad"
                            state.head_drop_pct  = drop
                    else:
                        with state_lock:
                            state.posture_status = "good"
                            state.head_drop_pct  = drop
                else:
                    slouching_since = None
                    with state_lock:
                        state.posture_status = "good"
                        state.head_drop_pct  = max(0.0, drop)

            time.sleep(check_interval)

    except Exception as exc:
        logger.error("Error: %s", exc)
    finally:
        logger.info("Stopped")
