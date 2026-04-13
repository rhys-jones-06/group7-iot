from picamera2 import Picamera2
import cv2
import numpy as np
import time

YOLO_ONNX_PATH = "yolov8n.onnx"
YOLO_INPUT_SIZE = 640
YOLO_NMS_THRESHOLD = 0.45
YOLO_PHONE_CLASS_ID = 67
PHONE_CONFIDENCE = 0.3
PERSON_CONFIDENCE = 0.2

def preprocess(frame):
    h, w = frame.shape[:2]
    ratio = min(YOLO_INPUT_SIZE / w, YOLO_INPUT_SIZE / h)
    new_w, new_h = int(w * ratio), int(h * ratio)
    resized = cv2.resize(frame, (new_w, new_h))
    canvas = np.full((YOLO_INPUT_SIZE, YOLO_INPUT_SIZE, 3), 114, dtype=np.uint8)
    pad_h = (YOLO_INPUT_SIZE - new_h) // 2
    pad_w = (YOLO_INPUT_SIZE - new_w) // 2
    canvas[pad_h:pad_h + new_h, pad_w:pad_w + new_w] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1.0 / 255.0, (YOLO_INPUT_SIZE, YOLO_INPUT_SIZE), swapRB=True, crop=False)
    return blob, ratio, pad_w, pad_h

def extract_detections(output, class_id, conf_threshold, ratio, pad_w, pad_h, frame_h, frame_w):
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

    x1 = np.clip(x1, 0, frame_w)
    y1 = np.clip(y1, 0, frame_h)
    x2 = np.clip(x2, 0, frame_w)
    y2 = np.clip(y2, 0, frame_h)

    nms_boxes = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1)
    indices = cv2.dnn.NMSBoxes(nms_boxes.tolist(), filtered_scores.tolist(), conf_threshold, YOLO_NMS_THRESHOLD)

    results = []
    if len(indices) > 0:
        for i in (indices.flatten() if isinstance(indices, np.ndarray) else indices):
            results.append({
                "x1": int(x1[i]),
                "y1": int(y1[i]),
                "x2": int(x2[i]),
                "y2": int(y2[i]),
                "conf": float(filtered_scores[i]),
            })
    return results

cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (640, 480)}))
cam.start()
time.sleep(2)

net = cv2.dnn.readNetFromONNX(YOLO_ONNX_PATH)

print("Press q to quit")

while True:
    frame = cam.capture_array()

    if len(frame.shape) == 3 and frame.shape[2] == 4:
        frame = frame[:, :, :3]

    frame_h, frame_w = frame.shape[:2]
    blob, ratio, pad_w, pad_h = preprocess(frame)
    net.setInput(blob)
    output = net.forward()

    phones = extract_detections(output, YOLO_PHONE_CLASS_ID, PHONE_CONFIDENCE, ratio, pad_w, pad_h, frame_h, frame_w)
    persons = extract_detections(output, 0, PERSON_CONFIDENCE, ratio, pad_w, pad_h, frame_h, frame_w)

    preview = frame.copy()

    for det in persons:
        cv2.rectangle(preview, (det["x1"], det["y1"]), (det["x2"], det["y2"]), (0, 255, 0), 2)
        cv2.putText(preview, f"PERSON {det['conf']:.2f}", (det["x1"], max(20, det["y1"] - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.circle(preview, (det["x1"] + 20, det["y1"]), 5, (255, 255, 0), -1)

    for det in phones:
        cv2.rectangle(preview, (det["x1"], det["y1"]), (det["x2"], det["y2"]), (0, 0, 255), 2)
        cv2.putText(preview, f"PHONE {det['conf']:.2f}", (det["x1"], max(20, det["y1"] - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.imshow("LockIn YOLO Preview", preview)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break

cam.close()
cv2.destroyAllWindows()