from picamera2 import Picamera2
import cv2
import numpy as np
import time

YOLO_ONNX_PATH = "yolov8n.onnx"
YOLO_INPUT_SIZE = 640
YOLO_NMS_THRESHOLD = 0.45

cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (640, 480)}))
cam.start()
time.sleep(2)

net = cv2.dnn.readNetFromONNX(YOLO_ONNX_PATH)

print("Running YOLO debug (Ctrl+C to stop)\n")

while True:
    frame = cam.capture_array()

    if frame.shape[2] == 4:
        frame = frame[:, :, :3]

    h, w = frame.shape[:2]

    # preprocess
    ratio = min(640 / w, 640 / h)
    new_w, new_h = int(w * ratio), int(h * ratio)
    resized = cv2.resize(frame, (new_w, new_h))
    canvas = np.full((640, 640, 3), 114, dtype=np.uint8)
    pad_h = (640 - new_h) // 2
    pad_w = (640 - new_w) // 2
    canvas[pad_h:pad_h+new_h, pad_w:pad_w+new_w] = resized

    blob = cv2.dnn.blobFromImage(canvas, 1/255.0, (640, 640), swapRB=True)
    net.setInput(blob)
    output = net.forward()

    predictions = output[0].T

    person_scores = predictions[:, 4]  # class 0
    mask = person_scores > 0.2

    if np.any(mask):
        boxes = predictions[mask, :4]
        scores = person_scores[mask]

        best = np.argmax(scores)

        cy, h_box = boxes[best, 1], boxes[best, 3]
        y1 = (cy - h_box / 2 - pad_h) / ratio
        head_y = y1 / h

        print(f"PERSON detected | head_y={head_y:.2f} | conf={scores[best]:.2f}")

    else:
        print("NO PERSON")

    time.sleep(0.5)