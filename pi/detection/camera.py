# ===========================================================================
# LockIn — pi/detection/camera.py
# CM2211 Group 07 | Feature F2: YOLOv8n Phone Detection
#
# PURPOSE:
#   Captures frames from the Pi Camera and runs YOLOv8n to detect phones.
#
# KEY CHANGE FROM ORIGINAL PLAN:
#   Instead of using the `ultralytics` pip package (which needs internet
#   to install), we load the YOLOv8n model as an ONNX file using OpenCV's
#   built-in DNN module. OpenCV comes pre-installed on Raspberry Pi OS,
#   so this needs ZERO pip installs. The only thing you copy via USB is
#   the yolov8n.onnx file itself.
#
# HOW IT WORKS:
#   1. Pi Camera captures frames at a capped frame rate (default 5 FPS).
#   2. Each frame is resized and formatted for the YOLO model input.
#   3. OpenCV's DNN module runs the ONNX model on the frame.
#   4. We parse the output to find "cell phone" detections (COCO class 67).
#   5. We apply filters: confidence threshold + height check (phone held
#      up vs flat on desk).
#   6. Result is written to shared_state for the main thread to read.
#
# PRIVACY (F7):
#   - ALL inference runs locally — no frames leave the device.
#   - No images saved to disk.
#   - LED turns on when camera opens, off when it closes.
#
# THIRD-PARTY CODE / MODELS:
#   - OpenCV DNN module (pre-installed on Raspberry Pi OS)
#     https://docs.opencv.org/4.x/d6/d0f/group__dnn.html
#   - YOLOv8n ONNX model from Ultralytics, pre-trained on the COCO dataset
#     https://docs.ultralytics.com/ | https://cocodataset.org/
#   - picamera2 (pre-installed on Raspberry Pi OS)
#     https://github.com/raspberrypi/picamera2
#
# USAGE:
#   Run in its own thread from main.py:
#     threading.Thread(target=start_phone_detection, args=(state, lock))
# ===========================================================================

import os
import time
import logging
import threading

# These are ALL pre-installed on Raspberry Pi OS — no pip needed
import cv2
import numpy as np

try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None
    logging.warning("[camera] picamera2 not found — camera won't work")

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    logging.warning("[camera] RPi.GPIO not available — LED indicator won't work")

from config import (
    CAMERA_ENABLED,
    CAMERA_FPS_CAP,
    CAMERA_RESOLUTION,
    YOLO_ONNX_PATH,
    YOLO_CONFIDENCE_THRESHOLD,
    YOLO_NMS_THRESHOLD,
    YOLO_PHONE_CLASS_ID,
    YOLO_INPUT_SIZE,
    PHONE_HEIGHT_RATIO,
    LED_PIN,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LED helper (F7: Privacy indicator)
# ---------------------------------------------------------------------------
def _set_led(on: bool):
    """Turn the camera-active LED on or off."""
    if GPIO is None:
        return
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LED_PIN, GPIO.OUT)
        GPIO.output(LED_PIN, GPIO.HIGH if on else GPIO.LOW)
    except Exception as exc:
        logger.warning(f"[camera] Could not set LED: {exc}")


# ---------------------------------------------------------------------------
# YOLO preprocessing — prepare a frame for the model
# ---------------------------------------------------------------------------
def _preprocess_frame(frame):
    """
    Prepare a camera frame for YOLOv8n input.

    YOLOv8n expects:
      - 640x640 pixels
      - RGB colour (not BGR — OpenCV uses BGR by default)
      - Pixel values normalised from 0–255 to 0.0–1.0
      - Shape: [1, 3, 640, 640] (batch, channels, height, width)

    This function also handles "letterboxing" — if the camera frame isn't
    square, we add grey padding so the image doesn't get stretched/squashed.

    Args:
        frame: numpy array (H, W, 3) in RGB format from picamera2

    Returns:
        blob:       the processed input ready for the model
        ratio:      how much we scaled the image (needed to map boxes back)
        pad_w:      horizontal padding added (in pixels)
        pad_h:      vertical padding added (in pixels)
    """
    img_h, img_w = frame.shape[:2]
    target = YOLO_INPUT_SIZE  # 640

    # Figure out the scaling factor — scale so the longest side = 640
    ratio = min(target / img_w, target / img_h)
    new_w = int(img_w * ratio)
    new_h = int(img_h * ratio)

    # Resize the frame
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # Create a 640x640 grey canvas and paste the resized image in the centre
    # (this is "letterboxing" — it preserves the aspect ratio)
    canvas = np.full((target, target, 3), 114, dtype=np.uint8)  # grey fill
    pad_h = (target - new_h) // 2  # padding on top
    pad_w = (target - new_w) // 2  # padding on left
    canvas[pad_h : pad_h + new_h, pad_w : pad_w + new_w] = resized

    # Convert to the format the model expects:
    # 1. BGR to RGB (OpenCV uses BGR, but picamera2 gives us RGB already,
    #    so we only need this if using OpenCV capture — keeping it for safety)
    # 2. Normalise pixel values: 0–255 → 0.0–1.0
    # 3. Rearrange from (H, W, C) to (C, H, W) — channels first
    # 4. Add a batch dimension: (C, H, W) → (1, C, H, W)
    blob = cv2.dnn.blobFromImage(
        canvas,
        scalefactor=1.0 / 255.0,  # normalise to 0–1
        size=(target, target),
        swapRB=False,  # picamera2 already gives RGB
        crop=False,
    )

    return blob, ratio, pad_w, pad_h


# ---------------------------------------------------------------------------
# YOLO postprocessing — parse the raw model output into detections
# ---------------------------------------------------------------------------
def _postprocess_output(output, ratio, pad_w, pad_h, frame_h, frame_w):
    """
    Parse the raw YOLOv8n output and extract phone detections.

    YOLOv8n output shape is [1, 84, 8400]:
      - 8400 = number of candidate detections (anchor boxes)
      - 84 = 4 (box coordinates: cx, cy, w, h) + 80 (class scores)

    We need to:
      1. Transpose so each row is one detection: [8400, 84]
      2. For each detection, find the highest class score
      3. Filter for "cell phone" class (ID 67) with sufficient confidence
      4. Convert box coordinates from model space back to original frame space
      5. Apply NMS (non-max suppression) to remove overlapping duplicates

    Args:
        output:   raw model output, shape [1, 84, 8400]
        ratio:    the scale factor used during preprocessing
        pad_w:    horizontal padding that was added
        pad_h:    vertical padding that was added
        frame_h:  original frame height in pixels
        frame_w:  original frame width in pixels

    Returns:
        list of (x1, y1, x2, y2, confidence) tuples for phone detections
    """
    # Reshape: [1, 84, 8400] → [8400, 84]
    # Each row is now one detection: [cx, cy, w, h, class0_score, class1_score, ...]
    predictions = output[0].T  # transpose from (84, 8400) to (8400, 84)

    # Split into box coordinates and class scores
    boxes_cxcywh = predictions[:, :4]      # first 4 columns: centre-x, centre-y, width, height
    class_scores = predictions[:, 4:]      # remaining 80 columns: one score per COCO class

    # We only care about the "cell phone" class (ID 67)
    phone_scores = class_scores[:, YOLO_PHONE_CLASS_ID]

    # Filter: keep only detections where the phone score is above our threshold
    mask = phone_scores > YOLO_CONFIDENCE_THRESHOLD
    if not np.any(mask):
        return []  # no phones detected

    filtered_boxes = boxes_cxcywh[mask]
    filtered_scores = phone_scores[mask]

    # Convert from centre-x,centre-y,width,height to x1,y1,x2,y2 (corners)
    # These are still in 640x640 model space — we need to map back to original frame
    x1 = filtered_boxes[:, 0] - filtered_boxes[:, 2] / 2  # cx - w/2
    y1 = filtered_boxes[:, 1] - filtered_boxes[:, 3] / 2  # cy - h/2
    x2 = filtered_boxes[:, 0] + filtered_boxes[:, 2] / 2  # cx + w/2
    y2 = filtered_boxes[:, 1] + filtered_boxes[:, 3] / 2  # cy + h/2

    # Remove the letterbox padding and undo the scaling
    x1 = (x1 - pad_w) / ratio
    y1 = (y1 - pad_h) / ratio
    x2 = (x2 - pad_w) / ratio
    y2 = (y2 - pad_h) / ratio

    # Clip to frame boundaries (make sure boxes don't go outside the image)
    x1 = np.clip(x1, 0, frame_w)
    y1 = np.clip(y1, 0, frame_h)
    x2 = np.clip(x2, 0, frame_w)
    y2 = np.clip(y2, 0, frame_h)

    # Non-max suppression: if YOLO detects the same phone multiple times
    # with overlapping boxes, keep only the most confident one
    boxes_for_nms = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1)  # x,y,w,h format for OpenCV
    indices = cv2.dnn.NMSBoxes(
        boxes_for_nms.tolist(),
        filtered_scores.tolist(),
        YOLO_CONFIDENCE_THRESHOLD,
        YOLO_NMS_THRESHOLD,
    )

    # Build the final list of detections
    detections = []
    if len(indices) > 0:
        # OpenCV NMS returns indices in different formats depending on version
        if isinstance(indices, np.ndarray):
            indices = indices.flatten()
        for i in indices:
            detections.append((
                float(x1[i]), float(y1[i]),
                float(x2[i]), float(y2[i]),
                float(filtered_scores[i]),
            ))

    return detections


# ---------------------------------------------------------------------------
# Check if a phone detection counts as "held up" (not flat on desk)
# ---------------------------------------------------------------------------
def _is_phone_held_up(y1, y2, frame_h):
    """
    Check if the phone bounding box is in the upper portion of the frame.

    If someone is holding their phone up to look at it, the phone appears
    in the upper ~70% of the camera frame. If the phone is just lying flat
    on the desk, it appears near the bottom of the frame.

    We only want to trigger alerts when the phone is being actively used
    (held up), not when it's just sitting on the desk.

    Args:
        y1, y2:   top and bottom of the bounding box in pixels
        frame_h:  total frame height in pixels

    Returns:
        True if the phone is in the "held up" zone
    """
    centre_y = (y1 + y2) / 2.0
    height_limit = frame_h * PHONE_HEIGHT_RATIO
    return centre_y < height_limit


# ---------------------------------------------------------------------------
# Main detection loop — runs in its own thread
# ---------------------------------------------------------------------------
def start_phone_detection(shared_state: dict, state_lock: threading.Lock):
    """
    Continuously capture frames and detect phones using YOLOv8n ONNX.
    Runs forever until shared_state["running"] is set to False.

    Updates in shared_state:
        - "phone_detected":   bool
        - "phone_confidence": float (0.0–1.0)
        - "latest_frame":     numpy array (shared with posture.py)

    Args:
        shared_state: global shared state dict
        state_lock:   threading.Lock for safe access
    """
    if not CAMERA_ENABLED:
        logger.info("[camera] Camera disabled in config — phone detection off")
        return

    if Picamera2 is None:
        logger.error("[camera] picamera2 not available — cannot start")
        return

    # ---- Check the ONNX model file exists ----
    if not os.path.isfile(YOLO_ONNX_PATH):
        logger.error(
            f"[camera] Model file not found: {YOLO_ONNX_PATH}\n"
            f"  Copy yolov8n.onnx into the pi/ folder via USB stick.\n"
            f"  See SETUP_GUIDE.md for instructions."
        )
        return

    # ---- Load the YOLO model using OpenCV DNN ----
    # This is the key bit: cv2.dnn can load ONNX files directly.
    # No pip install needed — OpenCV is pre-installed on the Pi.
    logger.info("[camera] Loading YOLOv8n ONNX model (this may take 10–30 seconds)...")
    net = cv2.dnn.readNetFromONNX(YOLO_ONNX_PATH)
    logger.info("[camera] Model loaded successfully")

    # ---- Open the Pi Camera ----
    camera = Picamera2()
    camera_config = camera.create_still_configuration(
        main={"size": (640, 480)}
    )
    camera.configure(camera_config)
    camera.start()
    _set_led(True)
    logger.info(
        f"[camera] Camera started at {CAMERA_RESOLUTION[0]}x{CAMERA_RESOLUTION[1]}, "
        f"FPS cap={CAMERA_FPS_CAP}, LED ON"
    )

    frame_interval = 1.0 / CAMERA_FPS_CAP

    try:
        while True:
            with state_lock:
                if not shared_state.get("running", True):
                    break
                if not shared_state.get("camera_enabled", True):
                    shared_state["phone_detected"] = False
                    shared_state["phone_confidence"] = 0.0
                    time.sleep(1.0)
                    continue

            loop_start = time.time()

            # ---- Capture a frame ----
            frame = camera.capture_array()
            frame_h, frame_w = frame.shape[:2]

            # ---- Preprocess for YOLO ----
            blob, ratio, pad_w, pad_h = _preprocess_frame(frame)

            # ---- Run inference ----
            net.setInput(blob)
            output = net.forward()  # shape: [1, 84, 8400]

            # ---- Parse results ----
            detections = _postprocess_output(output, ratio, pad_w, pad_h, frame_h, frame_w)

            # ---- Check if any detection is a phone being held up ----
            phone_found = False
            best_confidence = 0.0

            for (x1, y1, x2, y2, conf) in detections:
                if _is_phone_held_up(y1, y2, frame_h):
                    phone_found = True
                    if conf > best_confidence:
                        best_confidence = conf
                else:
                    logger.debug(f"[camera] Phone on desk (ignored) — conf {conf:.2f}")

            # ---- Update shared state ----
            with state_lock:
                shared_state["phone_detected"] = phone_found
                shared_state["phone_confidence"] = best_confidence
                shared_state["latest_frame"] = frame

            if phone_found:
                logger.info(f"[camera] Phone detected — confidence {best_confidence:.2f}")

            # ---- FPS cap ----
            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as exc:
        logger.error(f"[camera] Unexpected error: {exc}")

    finally:
        camera.stop()
        camera.close()
        _set_led(False)
        logger.info("[camera] Camera stopped, LED OFF")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("=== LockIn Camera Test (F2) ===")
    print("Hold a phone in front of the camera to test detection.")
    print("Press Ctrl+C to stop.\n")

    test_state = {
        "running": True,
        "camera_enabled": True,
        "phone_detected": False,
        "phone_confidence": 0.0,
        "latest_frame": None,
    }
    test_lock = threading.Lock()

    try:
        start_phone_detection(test_state, test_lock)
    except KeyboardInterrupt:
        test_state["running"] = False
        print("\nTest stopped.")
