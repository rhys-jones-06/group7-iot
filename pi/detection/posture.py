# ===========================================================================
# LockIn — pi/detection/posture.py
# CM2211 Group 07 | Feature F3: Posture / Slouch Detection
#
# HOW IT WORKS:
#   YOLO already detects you as a "person" every frame for F2.
#   The top of that bounding box = the top of your head.
#   
#   1. CALIBRATION: Sit properly for a few seconds. The system learns
#      where the top of your head normally is. "Return to this position"
#      is the baseline.
#   2. MONITORING: If the top of your head drops (you slouch down in
#      your chair), your head position sinks in the frame.
#      If it drops more than the threshold for 5+ seconds:
#      → "SIT UP STRAIGHT — return to starting position"
#   3. When you sit back up, the drop goes away and it shows "GOOD".
#
# WHY THIS IS BETTER THAN HAAR CASCADE:
#   - YOLO person detection is already running (no extra processing)
#   - Works even if you're not looking directly at the camera
#   - Much more reliable — YOLO rarely loses a person in frame
#   - Detects the whole body, not just the face
# ===========================================================================

import time
import logging
import threading

from config import (
    POSTURE_ENABLED, FACE_DROP_THRESHOLD,
    POSTURE_SUSTAINED_S, FACE_BASELINE_FRAMES,
    CAMERA_FPS_CAP,
)

logger = logging.getLogger(__name__)


def start_posture_detection(shared_state, state_lock):
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
                if not shared_state.get("running", True):
                    break
                head_y = shared_state.get("person_head_y")

            if head_y is None:
                # YOLO didn't detect a person — can't measure posture
                slouching_since = None
                with state_lock:
                    shared_state["posture_status"] = "no person"
                    shared_state["head_drop_pct"] = 0.0
                time.sleep(check_interval)
                continue

            now = time.time()

            # --- CALIBRATION PHASE ---
            if len(baseline_readings) < FACE_BASELINE_FRAMES:
                baseline_readings.append(head_y)

                if len(baseline_readings) == FACE_BASELINE_FRAMES:
                    baseline_y = sum(baseline_readings) / len(baseline_readings)
                    logger.info(
                        "Baseline calibrated: head top at %.1f%% of frame",
                        baseline_y * 100
                    )
                    logger.info(
                        "Sit like this = good posture. Slouching will be detected."
                    )

                with state_lock:
                    shared_state["posture_status"] = "calibrating"
                    shared_state["head_drop_pct"] = 0.0

            # --- MONITORING PHASE ---
            else:
                # head_y is the top of the bounding box (0 = top of frame, 1 = bottom)
                # If you slouch, your head drops, so head_y increases
                drop = head_y - baseline_y

                if drop > FACE_DROP_THRESHOLD:
                    # Head has sunk below baseline — slouching
                    if slouching_since is None:
                        slouching_since = now

                    duration = now - slouching_since

                    if duration >= POSTURE_SUSTAINED_S:
                        with state_lock:
                            shared_state["posture_status"] = "bad"
                            shared_state["head_drop_pct"] = drop
                    else:
                        # Dropping but not long enough — might be brief
                        with state_lock:
                            shared_state["posture_status"] = "good"
                            shared_state["head_drop_pct"] = drop

                else:
                    # Head at or above baseline — good posture
                    slouching_since = None
                    with state_lock:
                        shared_state["posture_status"] = "good"
                        shared_state["head_drop_pct"] = max(0.0, drop)

            time.sleep(check_interval)

    except Exception as exc:
        logger.error("Error: %s", exc)
    finally:
        logger.info("Stopped")
