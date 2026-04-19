# ===========================================================================
# LockIn — pi/detection/camera.py
# CM2211 Group 07 | F2: Phone Detection + F3: Person tracking for posture
#
# YOLO detects both phones AND people in every frame. We use:
#   - Phone detections → F2 (distraction alert)
#   - Person detection bounding box → F3 (posture/slouch tracking)
#
# The top of the person bounding box = top of your head.
# When you slouch, your head drops, so the top of the box drops.
# This is way more reliable than Haar cascade face detection.
# ===========================================================================

import os
import time
import logging
import threading
import cv2
import numpy as np

from state import GlobalState

try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from config import (
    CAMERA_ENABLED,
    CAMERA_FPS_CAP,
    YOLO_ONNX_PATH,
    YOLO_CONFIDENCE_THRESHOLD,
    YOLO_NMS_THRESHOLD,
    YOLO_PHONE_CLASS_ID,
    YOLO_INPUT_SIZE,
    PHONE_HEIGHT_RATIO,
    LED_PIN,
)

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0  # COCO class 0 = "person"
PERSON_CONFIDENCE = 0.2


def _set_led(on):
    if GPIO is None:
        return
    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LED_PIN, GPIO.OUT)
        GPIO.output(LED_PIN, GPIO.HIGH if on else GPIO.LOW)
    except Exception:
        pass


def _preprocess(frame):
    img_h, img_w = frame.shape[:2]
    target = YOLO_INPUT_SIZE
    ratio = min(target / img_w, target / img_h)
    new_w, new_h = int(img_w * ratio), int(img_h * ratio)
    resized = cv2.resize(frame, (new_w, new_h))
    canvas = np.full((target, target, 3), 114, dtype=np.uint8)
    pad_h = (target - new_h) // 2
    pad_w = (target - new_w) // 2
    canvas[pad_h : pad_h + new_h, pad_w : pad_w + new_w] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1.0 / 255.0, (target, target), swapRB=True, crop=False)
    return blob, ratio, pad_w, pad_h


def _extract_detections(output, class_id, conf_threshold, ratio, pad_w, pad_h, frame_h, frame_w):
    """Extract detections for a specific class from YOLO output."""
    predictions = output[0].T
    scores = predictions[:, 4 + class_id]
    mask = scores > conf_threshold
    if not np.any(mask):
        return []
    boxes = predictions[mask, :4]
    filtered_scores = scores[mask]
    x1 = (boxes[:, 0] - boxes[:, 2] / 2 - pad_w) / ratio
    y1 = (boxes[:, 1] - boxes[:, 3] / 2 - pad_h) / ratio
    x2 = (boxes[:, 0] + boxes[:, 2] / 2 - pad_w) / ratio
    y2 = (boxes[:, 1] + boxes[:, 3] / 2 - pad_h) / ratio
    x1, y1 = np.clip(x1, 0, frame_w), np.clip(y1, 0, frame_h)
    x2, y2 = np.clip(x2, 0, frame_w), np.clip(y2, 0, frame_h)
    nms_boxes = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1)
    indices = cv2.dnn.NMSBoxes(
        nms_boxes.tolist(), filtered_scores.tolist(), conf_threshold, YOLO_NMS_THRESHOLD
    )
    results = []
    if len(indices) > 0:
        for i in (indices.flatten() if isinstance(indices, np.ndarray) else indices):
            results.append(
                {
                    "y1": float(y1[i]),  # top of bounding box
                    "y2": float(y2[i]),  # bottom of bounding box
                    "x1": float(x1[i]),
                    "x2": float(x2[i]),
                    "conf": float(filtered_scores[i]),
                }
            )
    return results


def start_phone_detection(shared_state: GlobalState, state_lock: threading.Lock) -> None:
    if not CAMERA_ENABLED or Picamera2 is None:
        return
    if not os.path.isfile(YOLO_ONNX_PATH):
        logger.error("Model file not found: %s", YOLO_ONNX_PATH)
        return

    logger.info("Loading YOLOv8n ONNX model...")
    net = cv2.dnn.readNetFromONNX(YOLO_ONNX_PATH)
    logger.info("Model loaded")

    camera = Picamera2()
    camera.configure(camera.create_video_configuration(main={"size": (640, 480)}))
    camera.start()
    _set_led(True)
    logger.info("Camera started, LED ON")

    frame_interval = 1.0 / CAMERA_FPS_CAP

    try:
        while True:
            with state_lock:
                if not shared_state.running:
                    break

            loop_start = time.time()
            frame = camera.capture_array()

            if len(frame.shape) == 3 and frame.shape[2] == 4:
                frame = frame[:, :, :3]

            frame_h, frame_w = frame.shape[:2]
            blob, ratio, pad_w, pad_h = _preprocess(frame)
            net.setInput(blob)
            output = net.forward()

            # --- F2: PHONE DETECTION ---
            phones = _extract_detections(
                output,
                YOLO_PHONE_CLASS_ID,
                YOLO_CONFIDENCE_THRESHOLD,
                ratio,
                pad_w,
                pad_h,
                frame_h,
                frame_w,
            )
            phone_found = len(phones) > 0
            best_phone_conf = max([p["conf"] for p in phones], default=0.0)
            for det in phones:
                centre_y = (det["y1"] + det["y2"]) / 2.0
                if centre_y < frame_h * PHONE_HEIGHT_RATIO:
                    phone_found = True
                    best_phone_conf = max(best_phone_conf, det["conf"])

            # --- F3: PERSON DETECTION (for posture) ---
            persons = _extract_detections(
                output, PERSON_CLASS_ID, PERSON_CONFIDENCE, ratio, pad_w, pad_h, frame_h, frame_w
            )

            # Take the largest person (closest to camera)
            person_head_y = None
            if persons:
                largest = max(persons, key=lambda p: (p["x2"] - p["x1"]) * (p["y2"] - p["y1"]))
                # The TOP of the person bounding box = top of their head
                # Normalise to 0-1 (fraction of frame height)
                person_head_y = largest["y1"] / frame_h

            # --- UPDATE SHARED STATE ---
            with state_lock:
                shared_state.phone_detected = phone_found
                shared_state.phone_confidence = best_phone_conf
                shared_state.person_head_y = person_head_y  # None if no person seen
                shared_state.latest_frame = frame

            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as exc:
        logger.error("Error: %s", exc)
    finally:
        camera.stop()
        camera.close()
        _set_led(False)
        logger.info("Camera stopped, LED OFF")
