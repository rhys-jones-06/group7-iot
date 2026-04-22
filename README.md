# LockIn — CM2211 Group 07

An IoT focus monitor that uses a Raspberry Pi camera to detect phone use and
posture issues during Pomodoro study sessions, with a web dashboard for
analytics and a virtual pet that reflects your study habits.

---

## Repository Structure

```
lockin/
├── pi/                          # Raspberry Pi client
│   ├── main.py                  # Entry point — starts all threads (F1–F5)
│   ├── config.py                # Hardware constants + server config loader
│   ├── client.py                # HTTP client for server sync (F6)
│   ├── setup.sh                 # One-command headless Pi setup
│   ├── lockin.conf.example      # Template for /boot/lockin.conf
│   ├── detection/
│   │   ├── camera.py            # F2: YOLOv8n ONNX phone + person detection
│   │   └── posture.py           # F3: slouch detection via YOLO person bbox
│   ├── feedback/
│   │   ├── display.py           # F5: Grove RGB LCD countdown display
│   │   ├── alert.py             # F4: servo motor vibration
│   │   └── grove_rgb_lcd.py     # I2C LCD library (DexterIndustries, modified)
│   ├── sensors/
│   │   ├── light.py             # F4: ambient light sensor (buzzer suppression)
│   │   └── ultrasonic.py        # HC-SR04 test script
│   └── yolov8n.onnx             # YOLOv8n COCO model (third-party, Ultralytics)
│
└── server/                      # Flask web server (hosted on Cardiff OpenShift)
    ├── app.py                   # Application factory
    ├── models.py                # SQLAlchemy ORM models (F6, F8)
    ├── config.py                # Environment-based configuration
    ├── extensions.py            # Flask extensions (db, login, limiter)
    ├── validators.py            # Marshmallow request schemas
    ├── utils.py                 # Serialisation helpers
    ├── wsgi.py                  # WSGI entry point for OpenShift
    ├── seed.py                  # One-off script: create users + API keys
    ├── routes/
    │   ├── auth.py              # Login / logout / register
    │   ├── ingest.py            # POST /api/ingest/session — Pi → server (F6)
    │   ├── dashboard.py         # Analytics API endpoints (F8)
    │   └── settings.py          # User settings + lockin.conf download
    ├── templates/               # Jinja2 HTML templates
    └── static/                  # CSS + JS
```

---

## Features

| # | Feature | Location |
|---|---|---|
| F1 | Camera-based desk presence — timer pauses when no one is at the desk | `pi/main.py` |
| F2 | YOLOv8n phone detection — ONNX inference on Pi camera frames | `pi/detection/camera.py` |
| F3 | Posture detection — slouch tracking via YOLO person bounding box | `pi/detection/posture.py` |
| F4 | Escalating alerts — LED → buzzer → motor, suppressed in low light | `pi/main.py`, `pi/feedback/alert.py`, `pi/sensors/light.py` |
| F5 | Grove RGB LCD — live countdown + distraction count + colour state | `pi/feedback/display.py` |
| F6 | Web dashboard — custom Flask + SQLite, session ingest API | `server/` |
| F7 | Privacy by design — all inference on Pi, camera LED, zero frames sent | `pi/detection/camera.py`, `pi/config.py` |
| F8 | Session analytics — streaks, heatmaps, trends, leaderboard, virtual pet | `server/routes/dashboard.py` |

---

## Pi Setup (Headless — no monitor needed)

### 1. Flash the SD card
Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) and enable SSH + set a username/password in the OS customisation screen.

### 2. Prepare the boot partition
Plug the SD card into any computer. The `boot` partition appears as a USB drive. Copy these three files into it:

| File | Purpose |
|---|---|
| `lockin.conf` | Download from dashboard → Settings → Pi Device Setup |
| `ssh` | Empty file — enables SSH on first boot |
| `wpa_supplicant.conf` | WiFi credentials (template below) |

**`wpa_supplicant.conf` template:**
```
country=GB
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
network={
    ssid="YOUR_WIFI_NAME"
    psk="YOUR_WIFI_PASSWORD"
}
```

### 3. First-time setup (once only)
Insert the SD card, power on the Pi, wait ~60 seconds, then SSH in and run:

```bash
ssh pi@lockin.local
curl -sL https://raw.githubusercontent.com/c24057633/group-7-iot/appstart/pi/setup.sh | sudo bash
```

LockIn starts automatically on every boot after that.

**Check logs:**
```bash
sudo journalctl -u lockin -f
```

---

## Server Setup

### Local development
```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r ../requirements-server.txt
python seed.py          # create a test user + generate API key
flask run
```

### OpenShift deployment
The `Dockerfile` and `wsgi.py` are configured for Cardiff's OpenShift platform.
Set these environment variables in OpenShift:
```
FLASK_ENV=production
FLASK_SECRET_KEY=<random-32-char-string>
DATABASE_URL=sqlite:///lockin.db
LOG_LEVEL=INFO
```

---

## Third-Party Dependencies

### Pi
| Library | Version | Purpose | Source |
|---|---|---|---|
| picamera2 | system apt | Pi Camera capture | Raspberry Pi Foundation |
| opencv-python | system apt | ONNX inference via cv2.dnn | OpenCV |
| RPi.GPIO | 0.7.0 | GPIO: LED, buzzer, motor | Raspberry Pi Foundation |
| requests | 2.31.0 | HTTP POST to server | Python Requests |
| grovepi | latest | GrovePi+ HAT I/O | DexterIndustries |
| grove_rgb_lcd | included | I2C LCD driver | DexterIndustries (modified) |
| yolov8n.onnx | — | COCO object detection model | Ultralytics (pretrained) |

### Server
| Library | Version | Purpose |
|---|---|---|
| Flask | 3.0.x | Web framework |
| Flask-SQLAlchemy | 3.x | SQLite ORM |
| Flask-Login | 0.6.x | Session authentication |
| Flask-Limiter | 3.x | Rate limiting |
| marshmallow | 3.x | Request validation |
| Werkzeug | — | Password hashing (bundled with Flask) |

### Dashboard (CDN, no install)
| Library | Version | Purpose |
|---|---|---|
| Chart.js | 3.9.1 | Charts |
| GridStack | 10 | Draggable widget layout |
| DM Sans / Space Mono | — | Fonts (Google Fonts) |

---

## Privacy (F7)

- All YOLOv8n and posture inference runs **locally on the Pi** — no frames leave the device
- The camera-active LED (GPIO 24) turns on whenever the camera stream is open
- The server receives only aggregate data: counts, durations, scores — never images
- Phone and posture detection can be disabled per-user from the dashboard Settings page
- The SQLite database stores no personally identifiable information beyond username
