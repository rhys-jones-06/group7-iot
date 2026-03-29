# Light sensor in A2, light/button in D8
# Turn the light on when the light sensor also detects light.

import time
import grovepi

PIN_LIGHT_SENSOR = 2
PIN_LIGHT_BUTTON = 8

grovepi.pinMode(PIN_LIGHT_SENSOR,"INPUT")
grovepi.pinMode(PIN_LIGHT_BUTTON,"OUTPUT")

# Turn on LED once sensor exceeds threshold value.
# Value can go up to 1023, but seems to cap at 827.
THRESHOLD = 10


while True:
    sensor_value = grovepi.analogRead(PIN_LIGHT_SENSOR)

    if sensor_value > THRESHOLD:
        grovepi.digitalWrite(PIN_LIGHT_BUTTON,1)
    else:
        grovepi.digitalWrite(PIN_LIGHT_BUTTON,0)

    print(f"{sensor_value}")
    time.sleep(.5)
