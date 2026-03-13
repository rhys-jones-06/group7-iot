"""
F3 — Head Pose Distraction Detection
File: pi/detection/posture.py

Uses MediaPipe to estimate head pose and detect prolonged
downward gaze indicating distraction.

No images are stored or transmitted.
"""

import time
import threading

import cv2
import mediapipe as mp
import numpy as np


class PostureDetector:

    def __init__(
        self,
        pitch_threshold=25,
        distraction_time=5
    ):

        # Threshold configuration
        self.pitch_threshold = pitch_threshold
        self.distraction_time = distraction_time

        # Detection state
        self.distracted_posture = False

        self.down_start = None
        self.lock = threading.Lock()

        # MediaPipe Pose
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose()

    def calculate_pitch(self, nose, left_ear, right_ear):
        """
        Estimate pitch angle based on head landmarks.
        """

        ear_mid = (
            (left_ear[0] + right_ear[0]) / 2,
            (left_ear[1] + right_ear[1]) / 2
        )

        dx = nose[0] - ear_mid[0]
        dy = nose[1] - ear_mid[1]

        angle = np.degrees(np.arctan2(dy, dx))

        return angle

    def process_frame(self, frame):
        """
        Process frame and detect head posture.
        """

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.pose.process(rgb)

        if not result.pose_landmarks:
            self.reset()
            return

        landmarks = result.pose_landmarks.landmark

        nose = (landmarks[0].x, landmarks[0].y)
        left_ear = (landmarks[7].x, landmarks[7].y)
        right_ear = (landmarks[8].x, landmarks[8].y)

        pitch = self.calculate_pitch(nose, left_ear, right_ear)

        now = time.time()

        if pitch > self.pitch_threshold:

            if self.down_start is None:
                self.down_start = now

            elif now - self.down_start > self.distraction_time:
                with self.lock:
                    self.distracted_posture = True

        else:
            self.reset()

    def reset(self):
        """Reset distraction timer."""

        self.down_start = None

        with self.lock:
            self.distracted_posture = False

    def get_state(self):
        """Thread-safe state access."""

        with self.lock:
            return self.distracted_posture