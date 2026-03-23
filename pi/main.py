# ===========================================================================
# LockIn — pi/main.py
# CM2211 Group 07
#
# LOCAL-ONLY entry point. No network, no pip installs, no internet.
# Runs phone detection (F2) and posture detection (F3) on the Pi.
# Prints live status to the terminal.
#
# REQUIRES:
#   - Raspberry Pi OS with picamera2, opencv, numpy (all pre-installed)
#   - yolov8n.onnx file in this folder (copied via USB — see SETUP_GUIDE)
#   - Pi Camera connected
#
# HOW TO RUN:
#   cd ~/lockin/pi
#   python3 main.py
#
# Press Ctrl+C to stop.
# ===========================================================================

import time
import signal
import logging
import threading

from detection.camera import start_phone_detection
from detection.posture import start_posture_detection
from config import LOG_LEVEL

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state — every thread reads/writes through this dict
# ---------------------------------------------------------------------------
state_lock = threading.Lock()
shared_state = {
    # System
    "running": True,
    "camera_enabled": True,

    # F2 — camera.py
    "phone_detected": False,
    "phone_confidence": 0.0,
    "latest_frame": None,

    # F3 — posture.py
    "distracted_posture": False,
    "face_detected": False,
    "face_drop_pct": 0.0,

    # Distraction timing (managed by main loop)
    "distraction_start": None,
    "distraction_seconds": 0.0,
}

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
def _handle_shutdown(sig, frame):
    logger.info("Shutting down...")
    with state_lock:
        shared_state["running"] = False

signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)

# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------
def _format_status(phone, conf, face, drop, distracted, dist_secs):
    if phone:
        phone_str = f"PHONE ({conf:.0%})"
    else:
        phone_str = "no phone"

    if not face:
        posture_str = "no face"
    elif drop > 0.01:
        posture_str = f"drop {drop:.0%}"
    else:
        posture_str = "ok"

    if distracted:
        dist_str = f"!! DISTRACTED {dist_secs:.0f}s !!"
    else:
        dist_str = "focused"

    return f"  Phone: {phone_str:20s} | Head: {posture_str:12s} | {dist_str}"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print()
    print("=" * 60)
    print("  LockIn — Local Detection Mode (no internet needed)")
    print("  F2: Phone detection (YOLOv8n via OpenCV)")
    print("  F3: Head pose detection (Haar cascade)")
    print("=" * 60)
    print("  Hold a phone up to trigger F2.")
    print("  Look down for 5s to trigger F3.")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    # ---- Start threads ----
    camera_thread = threading.Thread(
        target=start_phone_detection,
        args=(shared_state, state_lock),
        daemon=True,
        name="camera-F2",
    )
    posture_thread = threading.Thread(
        target=start_posture_detection,
        args=(shared_state, state_lock),
        daemon=True,
        name="posture-F3",
    )

    logger.info("Starting camera thread (F2)...")
    camera_thread.start()
    time.sleep(2.0)

    logger.info("Starting posture thread (F3)...")
    posture_thread.start()

    logger.info("All threads running. Entering main loop.\n")

    try:
        while True:
            with state_lock:
                if not shared_state["running"]:
                    break
                phone = shared_state["phone_detected"]
                conf = shared_state["phone_confidence"]
                face = shared_state["face_detected"]
                drop = shared_state["face_drop_pct"]

            # Distracted if EITHER signal fires
            is_distracted = phone or shared_state.get("distracted_posture", False)

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

            # ---- WHERE ALERTS GO (F4) ----
            # if is_distracted:
            #     if dist_secs < 10:  alerts.flash_led()
            #     elif dist_secs < 20: alerts.sound_buzzer()
            #     else: alerts.vibrate_motor()
            # else:
            #     alerts.all_off()

            status = _format_status(phone, conf, face, drop, is_distracted, dist_secs)
            print(f"\r{status}", end="", flush=True)

            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    with state_lock:
        shared_state["running"] = False

    print("\n")
    logger.info("Waiting for threads to stop...")
    camera_thread.join(timeout=5.0)
    posture_thread.join(timeout=5.0)
    logger.info("Done. Goodbye!")


if __name__ == "__main__":
    main()
