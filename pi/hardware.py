import threading

# All grovepi and smbus calls must acquire this lock first.
# GrovePi communicates over I2C which is not thread-safe.
i2c_lock = threading.Lock()