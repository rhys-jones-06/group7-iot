"""
F2 — YOLOv8n Phone Detection
File: pi/detection/camera.py

Captures frames from Picamera2 and performs YOLOv8n inference
to detect a phone being held by the user.

Privacy:
All inference runs locally on the Raspberry Pi.
No frames are saved or transmitted.
"""

import time
import threading

import numpy as np
from picamera2 import Picamera2
from ultralytics import YOLO


class PhoneDetector:
    """
    YOLOv8n phone detector running on Raspberry Pi.
    """

    PHONE_CLASS_ID = 67  # COCO dataset class for "cell phone"

    def __init__(
        self,
        model_path="yolov8n.pt",
        confidence_threshold=0.6,
        fps_limit=5,
        upper_frame_ratio=0.7
    ):

        # Configurable thresholds
        self.confidence_threshold = confidence_threshold
        self.frame_interval = 1.0 / fps_limit
        self.upper_frame_ratio = upper_frame_ratio

        # Detection state exposed to main program
        self.phone_detected = False
        self.confidence = 0.0

        self.lock = threading.Lock()
        self.running = False

        # Load YOLO model
        self.model = YOLO(model_path)

        # Setup camera
        self.camera = Picamera2()
        self.camera.configure(
            self.camera.create_preview_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
        )

    def start(self):
        """Start camera stream."""
        self.camera.start()
        self.running = True

    def stop(self):
        """Stop camera stream."""
        self.running = False
        self.camera.stop()

    def process_frame(self):
        """
        Capture frame and run YOLO inference.
        """

        frame = self.camera.capture_array()
        height, width, _ = frame.shape

        results = self.model(frame, verbose=False)

        phone_found = False
        best_conf = 0.0

        for result in results:
            for box in result.boxes:

                cls = int(box.cls[0])
                conf = float(box.conf[0])

                if cls != self.PHONE_CLASS_ID:
                    continue

                if conf < self.confidence_threshold:
                    continue

                x1, y1, x2, y2 = box.xyxy[0]

                center_y = (y1 + y2) / 2

                # Check phone is held (upper region of frame)
                if center_y < height * self.upper_frame_ratio:

                    if conf > best_conf:
                        phone_found = True
                        best_conf = conf

        with self.lock:
            self.phone_detected = phone_found
            self.confidence = best_conf

    def run(self):
        """
        Continuous detection loop.
        Designed to run in a dedicated thread.
        """

        while self.running:

            start = time.time()

            self.process_frame()

            elapsed = time.time() - start
            sleep_time = max(0, self.frame_interval - elapsed)

            time.sleep(sleep_time)

    def get_state(self):
        """
        Thread-safe access for main program.
        """

        with self.lock:
            return self.phone_detected, self.confidence