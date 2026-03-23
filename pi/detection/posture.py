# ===========================================================================
# LockIn — pi/detection/posture.py
# CM2211 Group 07 | Feature F3: Head Pose Distraction Signal
#
# PURPOSE:
#   Detects when the user is looking down (e.g. at a phone in their lap)
#   by tracking their face position in the camera frame over time.
#
# KEY CHANGE FROM ORIGINAL PLAN:
#   Instead of MediaPipe (which needs pip install), we use OpenCV's Haar
#   cascade face detector. This ships with OpenCV on Raspberry Pi OS —
#   the XML file is already on your Pi at:
#     /usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml
#   So this needs ZERO pip installs and ZERO extra files.
#
# HOW IT WORKS:
#   1. Reads frames from shared_state["latest_frame"] (set by camera.py).
#   2. Runs OpenCV's Haar cascade face detector to find the user's face.
#   3. Tracks the vertical centre of the face across frames.
#   4. For the first ~30 frames, it builds a "baseline" — where the face
#      normally sits when the user is studying properly.
#   5. After that, if the face drops significantly below the baseline
#      (the user looked down), it starts a timer.
#   6. If the face stays low for 5+ seconds, it flags distracted_posture.
#   7. Looking back up resets the timer.
#
# WHY THIS CATCHES DISTRACTIONS:
#   When someone looks down at a phone in their lap, their face moves
#   lower in the camera frame. Even if the phone is hidden from the
#   camera, we can still detect the head movement.
#
# PRIVACY (F7):
#   - All processing is local. No face data leaves the Pi.
#   - No images stored.
#
# THIRD-PARTY CODE:
#   - OpenCV Haar cascades (pre-installed on Raspberry Pi OS)
#     https://docs.opencv.org/4.x/d2/d99/tutorial_js_face_detection.html
#     The cascade XML file is part of the OpenCV package, not our code.
#
# USAGE:
#   Run in its own thread from main.py:
#     threading.Thread(target=start_posture_detection, args=(state, lock))
# ===========================================================================

import os
import time
import logging
import threading

# Pre-installed on Raspberry Pi OS
import cv2
import numpy as np

from config import (
    POSTURE_ENABLED,
    FACE_DROP_THRESHOLD,
    POSTURE_SUSTAINED_S,
    FACE_BASELINE_FRAMES,
    CAMERA_FPS_CAP,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Find the Haar cascade file — it ships with OpenCV
# ---------------------------------------------------------------------------
# OpenCV installs cascade XML files in a standard location.
# We check a few common paths in case the Pi has a slightly different setup.
_CASCADE_CANDIDATES = [
    "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
    "/usr/share/opencv4/haarcascades/haarcascade_frontalface_alt2.xml",
    "/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
    # Fallback: use OpenCV's built-in data path
]


def _find_cascade_path():
    """Find a usable Haar cascade XML file on this system."""
    for path in _CASCADE_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


# ---------------------------------------------------------------------------
# Main posture detection loop
# ---------------------------------------------------------------------------
def start_posture_detection(shared_state: dict, state_lock: threading.Lock):
    """
    Continuously track face position to detect when the user looks down.
    Runs forever until shared_state["running"] is False.

    Reads from shared_state:
        - "latest_frame":   numpy array from camera.py
        - "running":        bool
        - "camera_enabled": bool

    Writes to shared_state:
        - "distracted_posture": bool — True if user looking down for 5+ sec
        - "face_detected":      bool — True if a face is visible
        - "face_drop_pct":      float — how far face has dropped (0 = normal)

    Args:
        shared_state: global shared state dict
        state_lock:   threading.Lock
    """
    if not POSTURE_ENABLED:
        logger.info("[posture] Posture detection disabled in config")
        return

    # ---- Load the Haar cascade ----
    cascade_path = _find_cascade_path()
    if cascade_path is None:
        logger.error(
            "[posture] Could not find Haar cascade XML file. "
            "Is python3-opencv installed? (It should be by default.)"
        )
        return

    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        logger.error(f"[posture] Failed to load cascade from {cascade_path}")
        return

    logger.info(f"[posture] Haar cascade loaded from {cascade_path}")

    # ---- Baseline tracking ----
    # For the first N frames, we record where the face normally sits.
    # After that, any significant downward shift = "looking down".
    baseline_readings = []         # list of face centre Y positions
    baseline_y = None              # the "normal" face Y position (set after N frames)
    looking_down_since = None      # timestamp when downward gaze started

    check_interval = 1.0 / CAMERA_FPS_CAP

    try:
        while True:
            # ---- Check if we should stop ----
            with state_lock:
                if not shared_state.get("running", True):
                    break
                if not shared_state.get("camera_enabled", True):
                    shared_state["distracted_posture"] = False
                    shared_state["face_detected"] = False
                    shared_state["face_drop_pct"] = 0.0
                    time.sleep(1.0)
                    continue
                frame = shared_state.get("latest_frame")

            if frame is None:
                time.sleep(0.1)
                continue

            loop_start = time.time()

            # ---- Detect faces ----
            # Convert to greyscale — Haar cascades only work on grey images
            grey = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

            # detectMultiScale finds faces at different sizes in the image.
            # Parameters:
            #   scaleFactor=1.1  — how much to shrink the image at each step
            #   minNeighbors=5   — how many detections needed to count as real
            #   minSize=(80,80)  — ignore tiny faces (probably not the user)
            faces = face_cascade.detectMultiScale(
                grey,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(80, 80),
            )

            frame_h = frame.shape[0]

            if len(faces) > 0:
                # If multiple faces detected, take the largest one
                # (most likely the user sitting closest to the camera)
                largest_face = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = largest_face

                # Calculate the vertical centre of the face
                # (as a fraction of the frame height, 0.0 = top, 1.0 = bottom)
                face_centre_y = (fy + fh / 2.0) / frame_h

                # ---- Build the baseline during the first N frames ----
                if len(baseline_readings) < FACE_BASELINE_FRAMES:
                    baseline_readings.append(face_centre_y)

                    if len(baseline_readings) == FACE_BASELINE_FRAMES:
                        # We have enough readings — calculate the average
                        baseline_y = sum(baseline_readings) / len(baseline_readings)
                        logger.info(
                            f"[posture] Baseline set: face normally at "
                            f"{baseline_y:.1%} of frame height "
                            f"(based on {FACE_BASELINE_FRAMES} frames)"
                        )

                    # While building baseline, don't flag anything
                    with state_lock:
                        shared_state["distracted_posture"] = False
                        shared_state["face_detected"] = True
                        shared_state["face_drop_pct"] = 0.0

                else:
                    # ---- Compare current position to baseline ----
                    drop = face_centre_y - baseline_y  # positive = face moved down
                    is_looking_down = drop > FACE_DROP_THRESHOLD

                    if is_looking_down:
                        if looking_down_since is None:
                            looking_down_since = time.time()
                            logger.debug(
                                f"[posture] Face dropped by {drop:.1%} "
                                f"(threshold: {FACE_DROP_THRESHOLD:.1%})"
                            )

                        duration = time.time() - looking_down_since
                        distracted = duration >= POSTURE_SUSTAINED_S

                        if distracted:
                            logger.info(
                                f"[posture] Distracted — looking down "
                                f"for {duration:.1f}s (drop: {drop:.1%})"
                            )
                    else:
                        if looking_down_since is not None:
                            logger.debug("[posture] User looked back up — timer reset")
                        looking_down_since = None
                        distracted = False

                    with state_lock:
                        shared_state["distracted_posture"] = distracted
                        shared_state["face_detected"] = True
                        shared_state["face_drop_pct"] = max(0.0, drop)

            else:
                # ---- No face found ----
                # This could mean the user left (F1 handles that via ultrasonic)
                # or the lighting is bad. Don't flag as distracted.
                looking_down_since = None

                with state_lock:
                    shared_state["distracted_posture"] = False
                    shared_state["face_detected"] = False
                    shared_state["face_drop_pct"] = 0.0

            # ---- Match camera frame rate ----
            elapsed = time.time() - loop_start
            sleep_time = check_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as exc:
        logger.error(f"[posture] Unexpected error: {exc}")

    finally:
        logger.info("[posture] Posture detection stopped")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("=== LockIn Posture Test (F3) ===")
    print("Sit normally for ~6 seconds (baseline calibration).")
    print("Then look down to trigger the distraction flag.")
    print("Press Ctrl+C to stop.\n")

    if Picamera2 is None:
        # Try importing here for the standalone test
        try:
            from picamera2 import Picamera2 as Picamera2Local
        except ImportError:
            print("ERROR: picamera2 not found.")
            exit(1)
    else:
        Picamera2Local = Picamera2

    test_state = {
        "running": True,
        "camera_enabled": True,
        "latest_frame": None,
        "distracted_posture": False,
        "face_detected": False,
        "face_drop_pct": 0.0,
    }
    test_lock = threading.Lock()

    def _feed_frames():
        cam = Picamera2Local()
        config = cam.create_still_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        cam.configure(config)
        cam.start()
        try:
            while test_state.get("running", True):
                frm = cam.capture_array()
                with test_lock:
                    test_state["latest_frame"] = frm
                time.sleep(0.2)
        finally:
            cam.stop()
            cam.close()

    def _print_status():
        while test_state.get("running", True):
            with test_lock:
                face = test_state.get("face_detected", False)
                drop = test_state.get("face_drop_pct", 0.0)
                dist = test_state.get("distracted_posture", False)
            face_str = "FACE" if face else "no face"
            status = "DISTRACTED" if dist else "ok"
            print(f"  {face_str:8s} | drop: {drop:+5.1%} | {status}")
            time.sleep(1.0)

    cam_thread = threading.Thread(target=_feed_frames, daemon=True)
    cam_thread.start()
    status_thread = threading.Thread(target=_print_status, daemon=True)
    status_thread.start()

    try:
        start_posture_detection(test_state, test_lock)
    except KeyboardInterrupt:
        test_state["running"] = False
        print("\nTest stopped.")
