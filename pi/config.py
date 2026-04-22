# ===========================================================================
# LockIn — pi/config.py
# CM2211 Group 07 — Internet of Things
# ===========================================================================

import configparser
import sys
from pathlib import Path

# ── Server connection (read from /boot/lockin.conf) ───────────────────────────

_SEARCH_PATHS = [
    Path('/boot/lockin.conf'),
    Path('/boot/firmware/lockin.conf'),   # Ubuntu 22.04 on Pi
    Path(__file__).parent / 'lockin.conf',  # local dev fallback
]


def load() -> dict:
    """Read server_url and api_key from /boot/lockin.conf."""
    cfg = configparser.ConfigParser()

    found = None
    for p in _SEARCH_PATHS:
        if p.exists():
            cfg.read(p)
            found = p
            break

    if found is None:
        print(
            '[LockIn] ERROR: lockin.conf not found.\n'
            '  Download it from the dashboard Settings page and copy to /boot/lockin.conf',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        return {
            'server_url': cfg.get('lockin', 'server_url').rstrip('/'),
            'api_key':    cfg.get('lockin', 'api_key').strip(),
        }
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f'[LockIn] ERROR: malformed lockin.conf — {e}', file=sys.stderr)
        sys.exit(1)


# ── F2 — Phone detection ───────────────────────────────────────────────────────

CAMERA_ENABLED = True
CAMERA_FPS_CAP = 2
YOLO_ONNX_PATH = "yolov8n.onnx"
YOLO_CONFIDENCE_THRESHOLD = 0.3
YOLO_NMS_THRESHOLD = 0.45
YOLO_PHONE_CLASS_ID = 67
YOLO_INPUT_SIZE = 640
PHONE_HEIGHT_RATIO = 0.70

# ── F3 — Posture detection ─────────────────────────────────────────────────────

POSTURE_ENABLED = True
FACE_DROP_THRESHOLD = 0.10       # head must drop 10% of frame height
POSTURE_SUSTAINED_S = 5.0        # must stay dropped for 5 seconds
FACE_BASELINE_FRAMES = 15        # calibration frames (~8 sec at 2fps)

# ── F4 — Alerts (GPIO pins) ────────────────────────────────────────────────────

BUZZER_PIN = 22
MOTOR_PIN = 23
LED_PIN = 24

# ── Logging ────────────────────────────────────────────────────────────────────

LOG_LEVEL = "INFO"
