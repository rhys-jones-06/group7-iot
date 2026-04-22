from picamera2 import Picamera2
import cv2
import numpy as np
import time

cam = Picamera2()
cam.configure(cam.create_still_configuration(main={"size": (640, 480)}))
cam.start()
time.sleep(2)
frame = cam.capture_array()
cam.close()

# Strip 4th channel if present
if frame.shape[2] == 4:
	frame = frame[:, :, :3]

print("Frame shape:", frame.shape)
cv2.imwrite("/home/pi/test_detect.jpg", frame)
print("Saved photo")

net = cv2.dnn.readNetFromONNX("yolov8n.onnx")
blob = cv2.dnn.blobFromImage(frame, 1/255.0, (640,640), swapRB=True, crop=False)
net.setInput(blob)
output = net.forward()
print("Model output shape:", output.shape)

predictions = output[0].T
scores = predictions[:, 4:]
max_scores = scores.max(axis=1)
best_classes = scores.argmax(axis=1)

top10 = np.argsort(max_scores)[-10:][::-1]
COCO_NAMES = {0:'person',39:'bottle',41:'cup',56:'chair',62:'tv',63:'laptop',67:'cell phone',73:'book'}
print("\nTop 10 Detections:")
for i in top10:
	cls = int(best_classes[i])
	conf = float(max_scores[i])
	name = COCO_NAMES.get(cls, f"class_{cls}")
	print(f" {name}: {conf:.1%}")
