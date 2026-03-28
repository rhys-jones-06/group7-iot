# Testing file for the "ultrasonic ranger".
# Use pin D4 for this test file.

import time

import grovepi

PIN_ULTRASONIC = 4


def get_distance() -> int:
    return grovepi.ultrasonicRead(PIN_ULTRASONIC)


if __name__ == "__main__":
    while True:
        try:
            print(get_distance())
        except KeyboardInterrupt:
            break

        time.sleep(0.1)
