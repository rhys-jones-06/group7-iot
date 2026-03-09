# LockIn — Software Requirements & Development Plan
### CM2211 Internet of Things | Group 07

> **For coders:** Feature numbers (F1–F8) are fixed submission identifiers.
> They must be used consistently across the poster, demo video, CodeCast, and
> all code comments. Do not rename or renumber them.

---

## Feature Summary

| # | Feature | Owner area | Marks criteria |
|---|---|---|---|
| F1 | Desk presence detection | Pi (sensors) | Implementation 30% |
| F2 | YOLOv8n phone detection | Pi (AI) | Implementation 30% |
| F3 | MediaPipe head pose distraction signal | Pi (AI) | Implementation 30% |
| F4 | Escalating alert system | Pi (feedback) | Implementation, Human Factors |
| F5 | Pomodoro timer + LCD/joystick UI | Pi (UI) | Human Factors 10% |
| F6 | Custom web dashboard + database | Web server | Implementation, Human Factors |
| F7 | Privacy-by-design | Pi + web | Privacy & Security 10% |
| F8 | Session analytics + daily streak | Pi + web | Data Management & Analytics |

---

## Repository Structure

```
lockin/
├── pi/                          # Everything that runs on the Raspberry Pi
│   ├── main.py                  # Entry point — starts all threads
│   ├── config.py                # All tuneable constants (thresholds, URLs, flags)
│   ├── detection/  --  Rhys
│   │   ├── camera.py            # F2: Pi Camera stream + YOLOv8n inference  
│   │   └── posture.py           # F3: MediaPipe head pose estimation  
│   ├── sensors/  --  Oliver
│   │   ├── ultrasonic.py        # F1: HC-SR04 desk presence  
│   │   └── light.py             # F4: ambient light for alert adaptation  
│   ├── feedback/  --  Oliver
│   │   ├── alerts.py            # F4: escalating LED/buzzer/motor logic
│   │   └── display.py           # F5: LCD state machine + joystick navigation
│   └── session/  --  Oliver
│       ├── timer.py             # F5: Pomodoro state machine
│       ├── streak.py            # F8: daily streak logic
│       ├── events.py            # F8: structured event logger
│       └── api_client.py        # F6/F8: HTTP POST to web server
│
├── server/  --  Rhys            # Web server (hosted on Cardiff OpenShift)
│   ├── app.py                   # Flask application entry point
│   ├── models.py                # SQLite database models (SQLAlchemy)
│   ├── seed.py                  # One-off script to create users + generate API keys
│   ├── routes/
│   │   ├── ingest.py            # POST /api/ingest/session — receives data from Pi
│   │   ├── auth.py              # POST /login, POST /logout, GET /login
│   │   └── dashboard.py        # GET /api/sessions, /api/stats/*
│   ├── static/
│   │   ├── js/
│   │   │   └── dashboard.js     # Chart rendering, live polling
│   │   └── css/
│   │       └── dashboard.css
│   └── templates/
│       ├── dashboard.html       # Main dashboard template
│       └── login.html
│
└── README.md                    # Required by proforma — setup, structure, deps
```

---

## Feature Requirements

### F1 — Desk Presence Detection
**File:** `pi/sensors/ultrasonic.py`

- HC-SR04 polls continuously, returns distance in cm
- If distance delta > threshold (person leaves chair) → pause session timer
- On return → resume timer
- Exposed as: `bool desk_occupied`
- Threshold configurable in `config.py`

---

### F2 — YOLOv8n Phone Detection
**File:** `pi/detection/camera.py`

- `picamera2` captures frames, capped at 5 FPS to manage CPU load
- YOLOv8n (COCO pretrained, `cell phone` class) runs inference per frame
- Detection triggers only if:
  - Confidence > 0.6 (configurable)
  - Bounding box centre Y is in the upper 70% of frame (phone held, not flat on desk)
- Exposed as: `bool phone_detected`, `float confidence`
- All inference runs locally — no frames leave the Pi (see F7)

---

### F3 — Head Pose Distraction Signal
**File:** `pi/detection/posture.py`

- MediaPipe Pose tracks head landmarks per frame
- Calculates pitch angle from nose/ear landmarks
- Downward gaze sustained >5s → secondary distraction flag
- Alert fires on `phone_detected` OR `distracted_posture` (either signal sufficient)
- Exposed as: `bool distracted_posture`
- Reduces false negatives: phone hidden from camera but student still looking down

---

### F4 — Escalating Alert System
**File:** `pi/feedback/alerts.py`, `pi/sensors/light.py`

Escalation ladder (resets when distraction clears):

| Level | Trigger | Action |
|---|---|---|
| 1 | 0–10s distraction | LED flash |
| 2 | 10–20s | Buzzer (skipped in low-light — LED only) |
| 3 | 20s+ | Motor vibration |

- Low-light detection: light sensor lux below threshold → suppress buzzer, use LED only
- Break mode: all alerts fully suppressed
- Takes `int distraction_level` input, fires appropriate GPIO outputs

---

### F5 — Pomodoro Timer + LCD/Joystick UI
**Files:** `pi/session/timer.py`, `pi/feedback/display.py`

**Timer states:** `idle → running → break → paused → idle`

- Default: 25 min focus / 5 min break, configurable via joystick settings screen
- Buzzer sounds at session/break end
- Break mode disables F2/F3 detection (phone use permitted)
- Timer state persists across reboots (written to JSON on every state change)

**LCD screens (joystick up/down to navigate, left/right to adjust, press to confirm):**

| Screen | Displays |
|---|---|
| Home | Countdown timer, current state (FOCUS / BREAK / IDLE) |
| Stats | Today's session count, distraction count |
| Streak | Current streak in days |
| Settings | Focus duration, break duration, alert sensitivity, mantra text |
| Break | Break countdown, "Phone OK" message |

---

### F6 — Custom Web Dashboard + Database
**Files:** `server/`, `pi/session/api_client.py`

**Why custom over ThingsBoard:** More demonstrable complexity for CodeCast, full control over analytics views, counts as a built feature not a configured service.

**Pi side (`api_client.py`):**
- After each session ends, POST JSON to `/api/events` on the web server
- Payload: `{ session_duration_mins, distraction_count, focus_score, streak_days, distraction_timeline[], timestamp }`
- Non-blocking (runs in its own thread, failures logged but don't crash Pi)

**Server side (Flask + SQLite):**

Database tables:
```
users:        id, username, password_hash, api_key (unique per Pi/user)
sessions:     id, user_id (FK), timestamp, duration_mins, distraction_count, focus_score, streak_days
distractions: id, session_id (FK), timestamp, type (phone|posture), confidence
```

API endpoints:
```
POST /api/ingest/session  — receive session data from Pi (auth: API key → looked up to user)
GET  /api/sessions        — return logged-in user's sessions as JSON
GET  /api/stats/summary   — aggregated stats for logged-in user
GET  /api/stats/weekly    — week-over-week focus score comparison
GET  /api/stats/heatmap   — distraction counts by hour-of-day for logged-in user
POST /login               — authenticate user, set session cookie
POST /logout              — clear session cookie
GET  /                    — serve dashboard HTML (login required)
```

**Dashboard views:**
- Live session status (polls `/api/sessions` every 10s)
- Focus score trend over time (line chart)
- Distraction frequency heatmap by hour of day
- Weekly summary: total focus time, average distractions, streak progress
- "You get distracted most at X:00" insight derived from heatmap data

**Hosting:** Cardiff OpenShift platform (provided by school, see proforma)

---

### F7 — Privacy by Design
**Files:** `config.py`, `pi/detection/camera.py`, `pi/feedback/display.py`

This is worth **10% of the final mark** as a standalone criterion — treat it as a proper feature.

- All YOLOv8 and MediaPipe inference runs **locally on the Pi** — zero frames sent over network
- Camera-active LED turns on whenever `picamera2` stream is open, off when closed
- User can disable camera entirely via joystick Settings screen (`CAMERA_ENABLED = False` in config) — system falls back to ultrasonic + posture-only detection
- Web server receives only aggregate data: counts, durations, scores — never images or raw frames
- SQLite database stores no PII
- `config.py` documents all privacy-relevant flags with comments

**Must be demonstrated in CodeCast:** show the network traffic (or lack of it), show the LED activating, show the camera disable toggle working.

---

### F8 — Session Analytics + Daily Streak
**Files:** `pi/session/streak.py`, `pi/session/events.py`, `server/routes/dashboard.py`

**Event logging (Pi side):**
- Append structured events to local `events.json`:
  - `focus_start`, `focus_end`, `distraction_detected`, `distraction_cleared`, `break_start`, `break_end`
- Each event: `{ type, timestamp, metadata }`
- Thread-safe (use a `threading.Lock`)
- Uploaded to server as part of session POST

**Streak logic:**
- Completed day = at least one full Pomodoro session finished
- Stored in `streak.json`: `{ streak: int, last_completed_date: str }`
- Checked on Pi startup: if `last_completed_date` was >1 calendar day ago, streak resets to 0
- Displayed on LCD (F5) and included in server POST (F6)

**Analytics (server side):**
- Focus score: `session_duration / (distraction_count + 1)` — normalised 0–100
- Weekly trend: compare this week's average focus score to last week's
- Insight strings generated server-side: "Your focus improved 18% this week", "Most distractions occur around 3pm"

---

## Architecture Overview

```
[Ultrasonic] ──┐
[Pi Camera]  ──┤── main.py (Pi) ──── session events ──── api_client.py ──── POST /api/events
[Light]      ──┤     │                                                           │
[Joystick]   ──┘     │                                                    [Flask Server]
                      │                                                    [SQLite DB]
               [LCD Display]                                               [Dashboard HTML/JS]
               [Buzzer/Motor/LED]                                               │
                                                                         [Student's browser]
```

All AI inference stays on the Pi. Only session summaries cross the network.

---

## Development Phases

### Phase 1 — Hardware Baseline (Week 1)
Verify every component produces output before writing logic. One test script per component.

| Task | File | Done when |
|---|---|---|
| Ultrasonic distance reading | `sensors/ultrasonic.py` | Prints cm values to console |
| Pi Camera frame capture | `detection/camera.py` | Saves a single JPEG to disk |
| LCD prints text | `feedback/display.py` | "Hello LockIn" visible on screen |
| Buzzer fires | `feedback/alerts.py` | Audible beep on GPIO trigger |
| Motor vibrates | `feedback/alerts.py` | Physical vibration confirmed |
| Joystick X/Y/button reads | `feedback/display.py` | Prints direction on move/press |
| Light sensor value | `sensors/light.py` | Different values in light vs dark |

---

### Phase 2 — Core Pi Logic (Weeks 2–3)
Build and test each module in isolation before wiring together.

| Task | File | Notes |
|---|---|---|
| YOLOv8n on static image | `detection/camera.py` | `pip install ultralytics`, confirm `cell phone` class detects |
| Live phone detection + height filter | `detection/camera.py` | Test with phone held vs flat on desk |
| MediaPipe pitch angle | `detection/posture.py` | Print angle live, confirm downward gaze threshold |
| Pomodoro state machine | `session/timer.py` | Unit test all state transitions in isolation |
| Escalating alerts | `feedback/alerts.py` | Manually pass distraction_level 1/2/3, verify outputs |
| LCD state machine | `feedback/display.py` | All 5 screens navigable, values adjustable |
| Event logger | `session/events.py` | Write events, confirm JSON structure, test lock |
| Streak logic | `session/streak.py` | Test: same day = no change, next day = increment, skip day = reset |

---

### Phase 3 — Web Server (Weeks 2–3, parallel track)
Can be developed independently of Pi hardware.

| Task | File | Notes |
|---|---|---|
| Flask app + SQLite schema | `server/app.py`, `models.py` | `pip install flask flask-sqlalchemy flask-login` |
| User seed script | `server/seed.py` | Creates user rows + generates API keys — run once |
| POST /api/ingest/session | `server/routes/ingest.py` | Look up user from API key, write session + distractions |
| GET /api/sessions + /api/stats/* | `server/routes/dashboard.py` | Filter all queries by `current_user.id` |
| Login/logout routes | `server/routes/auth.py` | `flask-login`, `werkzeug.security` for password hash |
| Dashboard HTML + charts | `templates/`, `static/js/` | Use Chart.js (CDN), no framework needed |
| Live polling | `static/js/dashboard.js` | `setInterval` polling `/api/sessions` every 10s |
| Deploy to OpenShift | — | Cardiff school platform — see proforma links |

---

### Phase 4 — Integration (Week 4)
Wire Pi modules into `main.py` with threaded main loop.

**Thread model:**
```
Thread 1 (fast, ~20Hz): ultrasonic + light sensor polling
Thread 2 (5 FPS cap):   camera inference (F2) + head pose (F3)
Thread 3 (UI loop):     LCD update + joystick input (F5)
Thread 4 (on demand):   api_client POST to server (F6/F8)
Main thread:            orchestration — reads shared state, drives alert escalation (F4)
```

**Shared state (use locks):**
```python
state = {
    "desk_occupied": False,
    "phone_detected": False,
    "distracted_posture": False,
    "distraction_start": None,
    "timer_state": "idle",
    "timer_remaining": 1500,
    "streak": 0,
}
```

---

### Phase 5 — Polish + Privacy + Demo Prep (Weeks 5–6)

- [ ] Camera LED activates/deactivates correctly with stream open/close
- [ ] Camera disable toggle in settings works end-to-end (F7)
- [ ] Confirm zero image data leaves Pi (check server logs)
- [ ] Full `config.py` with all thresholds documented
- [ ] Run 3 complete Pomodoro cycles — verify streak increments, server receives data, dashboard updates
- [ ] Dashboard analytics strings generating correctly ("improved X% this week")
- [ ] README written (required by proforma — setup, folder structure, third-party libs + versions)
- [ ] All code comments identify third-party sections vs written-from-scratch (CodeCast requirement)
- [ ] Stress test: Pi running for 2+ hours, no memory leak or thread deadlock

---

## Key Dependencies

**Pi:**
```
picamera2       # Pi Camera capture
ultralytics     # YOLOv8n — F2
mediapipe       # Head pose — F3
RPi.GPIO        # GPIO: ultrasonic, buzzer, motor, LED, joystick
RPLCD           # LCD I2C — F5
requests        # HTTP POST to server — F6
```

**Server:**
```
flask               # Web framework
flask-sqlalchemy    # SQLite ORM
flask-login         # Session auth
werkzeug            # Password hashing (comes with flask)
```

**Dashboard (CDN, no install):**
```
Chart.js        # Charts
```

---

## Submission Checklist (from proforma)

### Code
- [ ] Feature numbers F1–F8 appear in comments wherever that feature's code lives
- [ ] Third-party code sections clearly commented as such
- [ ] `README.md` in repo root: folder structure, setup steps, all third-party deps with versions
- [ ] No passwords or access restrictions on the zip

### Poster
- [ ] Each feature marked with a red circle (RGB 192,0,0), 2cm diameter, feature number in white
- [ ] Architecture/data flow diagram included and fully labelled
- [ ] Each feature discussed across: functionality, implementation, complexity, quality, relevance, creativity, course concepts

### Videos
- [ ] Demo: no code shown, aimed at non-technical audience
- [ ] CodeCast: features discussed in F1→F8 order (penalty for wrong order)
- [ ] CodeCast: code runs live on screen, not screenshots
- [ ] CodeCast: F7 privacy features explicitly demonstrated (network traffic, LED, disable toggle)
- [ ] Everything claimed on poster is shown in CodeCast — no unsubstantiated claims

### High-mark targets
- [ ] F2: YOLOv8n running live on Pi with height heuristic for false positive reduction
- [ ] F3: MediaPipe as independent second distraction signal
- [ ] F6: Custom dashboard with analytics insights, not just raw data display
- [ ] F7: Privacy-by-design demonstrable and documented (worth 10% standalone)
- [ ] Cisco Packet Tracer hybrid simulation — explicitly rewarded, attempt if time allows
