# ===========================================================================
# LockIn — config.py
# CM2211 Group 07
# ===========================================================================

# F2 — Phone detection
CAMERA_ENABLED = True
CAMERA_FPS_CAP = 2
YOLO_ONNX_PATH = "yolov8n.onnx"
YOLO_CONFIDENCE_THRESHOLD = 0.3
YOLO_NMS_THRESHOLD = 0.45
YOLO_PHONE_CLASS_ID = 67
YOLO_INPUT_SIZE = 640
PHONE_HEIGHT_RATIO = 0.70

# F3 — Posture (slouch = head drops from starting position)
POSTURE_ENABLED = True
FACE_DROP_THRESHOLD = 0.10            # head must drop 10% of frame height
POSTURE_SUSTAINED_S = 5.0             # must stay dropped for 5 seconds
FACE_BASELINE_FRAMES = 15             # calibration frames (~8 sec at 2fps)

# F4 — Alerts
LIGHT_PIN = 2  # Analogue pin, cannot conflict with joystick using 2 data pins (0, 1)
BUZZER_PIN = 22
MOTOR_PIN = 23
LED_PIN = 24
LIGHT_THRESHOLD = 200  # Up to 1024, but realistic values are up to 800.

# F5 — Pomodoro
DEFAULT_FOCUS_MINS = 25
DEFAULT_BREAK_MINS = 5

# Logging
LOG_LEVEL = "INFO"
