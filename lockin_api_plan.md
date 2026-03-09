# LockIn — API Plan
### CM2211 Group 07

---

## Overview

Two distinct communication channels:

| Channel | Direction | Auth | Purpose |
|---|---|---|---|
| Pi → Server | POST | API key header | Ingest session data |
| Browser → Server | GET | Session cookie | Dashboard data |
| Browser → Server | POST | Session cookie | User login/logout |

---

## Authentication

### Pi → Server: API Key (per user)
- Pi includes its key in every request header: `X-API-Key: <key>`
- Key stored in `pi/config.py` and in the `users` table server-side
- Server looks up the user from the key, attaches session data to that user
- Server rejects any ingest request missing or with wrong key with `401`
- Each Pi/user gets a unique key — one key cannot access another user's data

### Browser → Server: Session Login
- `flask-login` handles session cookies
- Dashboard routes decorated with `@login_required` — redirect to `/login` if not authenticated
- Password hashed with `werkzeug.security`
- All `/api/stats/*` and `/api/sessions` routes filter by the logged-in user automatically
- No self-registration — admin creates users directly in the DB (acceptable for coursework scope)

---

## Database Schema

```sql
-- One row per registered user / Pi device
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    api_key       TEXT NOT NULL UNIQUE   -- Pi uses this to authenticate ingest requests
);

-- One row per completed Pomodoro session
CREATE TABLE sessions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id),
    timestamp         TEXT NOT NULL,        -- ISO 8601, e.g. "2026-03-09T14:32:00"
    duration_mins     REAL NOT NULL,        -- actual focus time (may be < 25 if abandoned)
    distraction_count INTEGER NOT NULL,
    focus_score       REAL NOT NULL,        -- duration / (distraction_count + 1), normalised 0-100
    streak_days       INTEGER NOT NULL
);

-- One row per individual distraction event within a session
CREATE TABLE distractions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(id),
    timestamp    TEXT NOT NULL,
    type         TEXT NOT NULL,   -- "phone" | "posture"
    confidence   REAL             -- null for posture type
);
```

---

## Endpoints

### Ingest (Pi → Server)

---

#### `POST /api/ingest/session`
Receives a completed session summary from the Pi.

**Auth:** `X-API-Key` header required — server looks up user from this key, attaches session to that user

**Request body:**
```json
{
  "timestamp": "2026-03-09T14:32:00",
  "duration_mins": 24.5,
  "distraction_count": 3,
  "focus_score": 81.7,
  "streak_days": 5,
  "distractions": [
    { "timestamp": "2026-03-09T14:10:00", "type": "phone", "confidence": 0.87 },
    { "timestamp": "2026-03-09T14:18:30", "type": "posture", "confidence": null },
    { "timestamp": "2026-03-09T14:25:10", "type": "phone", "confidence": 0.91 }
  ]
}
```

**Responses:**

| Status | Meaning |
|---|---|
| `201 Created` | Session and distractions written to DB |
| `400 Bad Request` | Missing or invalid fields — body contains error detail |
| `401 Unauthorized` | Missing or invalid API key |

**Response body (201):**
```json
{ "session_id": 42 }
```

---

### Dashboard Data (Browser → Server)

All routes below require session cookie (`@login_required`). Return `401` if not authenticated.

---

#### `GET /api/sessions`
Returns all sessions, newest first. Used by the main dashboard table/chart.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 50 | Max sessions to return |
| `offset` | int | 0 | Pagination offset |

**Response (200):**
```json
{
  "sessions": [
    {
      "id": 42,
      "timestamp": "2026-03-09T14:32:00",
      "duration_mins": 24.5,
      "distraction_count": 3,
      "focus_score": 81.7,
      "streak_days": 5
    }
  ],
  "total": 120
}
```

---

#### `GET /api/stats/summary`
Aggregated stats for the dashboard header cards.

**Response (200):**
```json
{
  "current_streak": 5,
  "total_sessions_today": 3,
  "total_focus_mins_today": 72.0,
  "avg_focus_score_this_week": 78.4,
  "avg_focus_score_last_week": 66.1,
  "week_over_week_change_pct": 18.6
}
```

---

#### `GET /api/stats/heatmap`
Distraction counts grouped by hour of day, across all sessions. Used to generate the "most distracted at X:00" insight.

**Response (200):**
```json
{
  "heatmap": [
    { "hour": 0,  "count": 0 },
    { "hour": 1,  "count": 0 },
    ...
    { "hour": 14, "count": 23 },
    { "hour": 15, "count": 31 },
    ...
    { "hour": 23, "count": 2 }
  ],
  "peak_hour": 15,
  "insight": "You get distracted most around 3:00 PM"
}
```

---

#### `GET /api/stats/trend`
Focus scores over the last N days, one data point per day (average). Used for the line chart.

**Query params:**

| Param | Type | Default |
|---|---|---|
| `days` | int | 14 |

**Response (200):**
```json
{
  "trend": [
    { "date": "2026-02-24", "avg_focus_score": 61.2, "session_count": 2 },
    { "date": "2026-02-25", "avg_focus_score": 68.4, "session_count": 3 },
    ...
  ]
}
```

---

### Auth (Browser → Server)

---

#### `POST /login`
Standard form POST. Handled by `flask-login`.

**Form fields:** `username`, `password`

**Responses:**

| Status | Meaning |
|---|---|
| `302` redirect to `/` | Login successful |
| `200` (re-render login with error) | Wrong credentials |

---

#### `POST /logout`
Clears session cookie.

**Response:** `302` redirect to `/login`

---

#### `GET /login`
Renders login page. Redirects to `/` if already authenticated.

---

### Dashboard Pages (Browser → Server)

| Route | Auth | Description |
|---|---|---|
| `GET /` | Required | Main dashboard — charts, summary cards, heatmap |
| `GET /login` | None | Login form |

---

## Pi Client (`pi/session/api_client.py`)

The Pi only calls one endpoint. Keep the client simple.

```python
import requests
import logging
from config import SERVER_URL, API_KEY

def post_session(session_data: dict) -> bool:
    """
    POST session summary to server. Returns True on success, False on failure.
    Never raises — failures are logged but must not crash the Pi.
    """
    try:
        resp = requests.post(
            f"{SERVER_URL}/api/ingest/session",
            json=session_data,
            headers={"X-API-Key": API_KEY},
            timeout=10
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logging.warning(f"[api_client] Failed to post session: {e}")
        return False
```

Key rules:
- Always `timeout=10` — Pi must not block indefinitely if server is down
- Never raise exceptions — a network failure must not interrupt the study session
- Log failures locally so they can be shown in CodeCast

---

## Error Handling Conventions

All API error responses follow the same structure:

```json
{
  "error": "missing_field",
  "detail": "duration_mins is required"
}
```

| Code | Used for |
|---|---|
| `400` | Malformed request body, missing fields, invalid types |
| `401` | Wrong/missing API key, not logged in |
| `404` | Session ID not found |
| `500` | Unexpected server error (log server-side, don't expose detail to client) |

---

## Config & Environment Variables

**Server (set as OpenShift env vars — never commit to repo):**
```
FLASK_SECRET_KEY=<random 32-char string>
DATABASE_URL=sqlite:///lockin.db
```

> Users and their API keys are created directly in the DB.
> No credentials are hardcoded — API keys in `pi/config.py` must be added
> to `.gitignore` or a separate secrets file before the repo is submitted.

---

## Implementation Order

1. `POST /api/ingest/session` + DB schema — unblock Pi team first
2. `GET /api/sessions` — needed for basic dashboard table
3. `GET /api/stats/summary` — header cards
4. `GET /api/stats/trend` — line chart
5. `GET /api/stats/heatmap` — insight string
6. Login/logout + `@login_required` on all above routes
7. Deploy to OpenShift, update `SERVER_URL` in Pi config, end-to-end test
