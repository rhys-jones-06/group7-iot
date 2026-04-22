from picamera2 import Picamera2
import time
cam = Picamera2()
config = cam.create_still_configuration()
cam.configure(config)
cam.start()
time.sleep(2)
cam.capture_file("/home/pi/test_photo.jpg")
main = {"size": CAMERA_RESOLUTION}
print("Photo saved to /home/pi/test_photo.jpg")
cam.close()
