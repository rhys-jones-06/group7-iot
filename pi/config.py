# ===========================================================================
# LockIn — config.py
# CM2211 Group 07
#
# All tuneable constants live here. Import this from any Pi module.
#
# OFFLINE MODE: This entire system runs with ZERO internet.
# The only libraries used are ones pre-installed on Raspberry Pi OS:
#   - picamera2, OpenCV (cv2), numpy, RPi.GPIO
# The only file you transfer via USB is yolov8n.onnx (~6 MB).
# ===========================================================================

# ---------------------------------------------------------------------------
# F2 — Phone detection (camera + YOLOv8n via OpenCV DNN)        [PRIVACY: F7]
# All inference runs locally — no frames leave the Pi.
# ---------------------------------------------------------------------------
CAMERA_ENABLED = True                 # user can disable via joystick settings
CAMERA_FPS_CAP = 5                    # max frames per second (keeps CPU cool)
CAMERA_RESOLUTION = (640, 480)        # width x height

# Path to the ONNX model file — copied onto the Pi via USB stick.
# This is the ONLY external file you need. See SETUP_GUIDE.md.
YOLO_ONNX_PATH = "yolov8n.onnx"

YOLO_CONFIDENCE_THRESHOLD = 0.3       # ignore detections below this confidence
YOLO_NMS_THRESHOLD = 0.45             # non-max suppression (removes overlapping boxes)
YOLO_PHONE_CLASS_ID = 67              # COCO class ID for "cell phone"
YOLO_INPUT_SIZE = 640                 # model expects 640x640 input
PHONE_HEIGHT_RATIO = 0.70             # bounding box centre must be in upper 70% of frame

# ---------------------------------------------------------------------------
# F3 — Posture / head-drop detection (OpenCV Haar cascade)
# Uses haarcascade_frontalface_default.xml that ships with OpenCV.
# No extra files or pip installs needed.
# ---------------------------------------------------------------------------
POSTURE_ENABLED = True
FACE_DROP_THRESHOLD = 0.15            # if face centre drops this fraction of frame
                                      # height below baseline → "looking down"
POSTURE_SUSTAINED_S = 5.0             # must be sustained this many seconds to flag
FACE_BASELINE_FRAMES = 30             # frames to average for "normal" face position

# ---------------------------------------------------------------------------
# F1 — Desk presence (ultrasonic)
# ---------------------------------------------------------------------------
ULTRASONIC_TRIGGER_PIN = 17
ULTRASONIC_ECHO_PIN = 27
DESK_PRESENCE_THRESHOLD_CM = 80
ULTRASONIC_POLL_INTERVAL_S = 0.05

# ---------------------------------------------------------------------------
# F4 — Escalating alerts
# ---------------------------------------------------------------------------
BUZZER_PIN = 22
MOTOR_PIN = 23
LED_PIN = 24                          # camera-active indicator LED
ALERT_LEVEL_1_S = 0
ALERT_LEVEL_2_S = 10
ALERT_LEVEL_3_S = 20
LOW_LIGHT_THRESHOLD_LUX = 50

# ---------------------------------------------------------------------------
# F5 — Pomodoro timer defaults
# ---------------------------------------------------------------------------
DEFAULT_FOCUS_MINS = 25
DEFAULT_BREAK_MINS = 5

# ---------------------------------------------------------------------------
# F7 — Privacy flags
# No frames stored to disk or sent over network. Ever.
# LED on LED_PIN activates when camera stream is open.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = "INFO"
