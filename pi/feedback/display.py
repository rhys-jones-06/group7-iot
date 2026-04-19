import time

import grovepi
from grove_rgb_lcd import setRGB, setText

# The Grove Thumb Joystick is an analog device that outputs analog signal ranging from 0 to 1023
# The X and Y axes are two ~10k potentiometers and a momentary push button which shorts the x axis

PIN_JOYSTICK_X = 0
PIN_JOYSTICK_Y = 1

grovepi.pinMode(PIN_JOYSTICK_X, "INPUT")
grovepi.pinMode(PIN_JOYSTICK_Y, "INPUT")

# Pos X to the right, pos Y up, with text on back upright.
# The joystick defines its own zones, so there is no calibration for deadzones.
# I.e. the X value is usually around 256, 512, 768, 1023.
# There are very small areas to have variability, so there is little in fine control.
# It is easy when selecting one direction to affect the other axis greatly, but not all the way to max/min.

# My values:
#    Min      Typ      Max      Click
# X  254-256  513-514  767-768  1023
# Y  251-252  511      773-774  <input>


if __name__ == "__main__":
    # RGB values 0-255
    setRGB(50, 50, 50)
    setText("Hello LockIn")

    while True:
        x = grovepi.analogRead(PIN_JOYSTICK_X)
        y = grovepi.analogRead(PIN_JOYSTICK_Y)

        click = 1 if x >= 1020 else 0

        print("x =", x, " y =", y, " click =", click)
        time.sleep(0.5)
