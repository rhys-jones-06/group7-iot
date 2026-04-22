# ===========================================================================
# test_posture.py — Posture detection test using YOLO person detection
#
# 1. Sit with GOOD posture for readings 1-8 (baseline)
# 2. Then SLOUCH for readings 9-16
# 3. The drop should be 10%+ when slouching
# ===========================================================================

from picamera2 import Picamera2
import cv2
import numpy as np
import time

cam = Picamera2()
cam.configure(cam.create_still_configuration(main={"size": (640, 480)}))
cam.start()
time.sleep(2)

net = cv2.dnn.readNetFromONNX("yolov8n.onnx")

print()
print("=" * 55)
print("  POSTURE TEST (uses YOLO person detection)")
print("=" * 55)
print()
print("  Readings 1-8:  sit with GOOD posture")
print("  Readings 9-16: SLOUCH in your chair")
print()
print("  Starting in 3 seconds — sit up straight!")
time.sleep(3)

baseline = []
baseline_y = None

for i in range(16):
    frame = cam.capture_array()
    if len(frame.shape) == 3 and frame.shape[2] == 4:
        frame = frame[:, :, :3]

    frame_h, frame_w = frame.shape[:2]

    # Run YOLO
    target = 640
    ratio = min(target / frame_w, target / frame_h)
    new_w, new_h = int(frame_w * ratio), int(frame_h * ratio)
    resized = cv2.resize(frame, (new_w, new_h))
    canvas = np.full((target, target, 3), 114, dtype=np.uint8)
    pad_h = (target - new_h) // 2
    pad_w = (target - new_w) // 2
    canvas[pad_h:pad_h + new_h, pad_w:pad_w + new_w] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1/255.0, (target, target), swapRB=True, crop=False)
    net.setInput(blob)
    output = net.forward()

    # Find person detections (class 0)
    predictions = output[0].T
    person_scores = predictions[:, 4]  # class 0 = person
    mask = person_scores > 0.3
    
    if i == 8:
        print()
        print("--- NOW SLOUCH DOWN IN YOUR CHAIR ---")
        print()

    if np.any(mask):
        boxes = predictions[mask, :4]
        scores = person_scores[mask]
        best_idx = np.argmax(scores)
        
        # Get top of bounding box (y1) in original frame coordinates
        cy, h_box = boxes[best_idx, 1], boxes[best_idx, 3]
        y1 = (cy - h_box / 2 - pad_h) / ratio
        head_y = y1 / frame_h  # normalised 0-1

        if i < 8:
            baseline.append(head_y)
            if i == 7:
                baseline_y = sum(baseline) / len(baseline)
            print("  {:2d}. Head top at {:.1%}  [BASELINE]  (person conf: {:.0%})".format(
                i + 1, head_y, float(scores[best_idx])
            ))
        else:
            if baseline_y:
                drop = head_y - baseline_y
                tag = ""
                if drop > 0.10:
                    tag = " <-- SLOUCHING (would trigger alert)"
                elif drop > 0.05:
                    tag = " <-- slight drop"
                print("  {:2d}. Head top at {:.1%}  drop: {:+.1%}{}".format(
                    i + 1, head_y, drop, tag
                ))
            else:
                print("  {:2d}. Head top at {:.1%}".format(i + 1, head_y))
    else:
        print("  {:2d}. NO PERSON DETECTED".format(i + 1))

    time.sleep(2)

cam.close()
print()
if baseline_y:
    print("  Your baseline (good posture): head top at {:.1%}".format(baseline_y))
    print("  Slouch threshold: {:.1%}".format(baseline_y + 0.10))
    print()
    print("  If 'SLOUCHING' appeared when you slouched, F3 works!")
print()
