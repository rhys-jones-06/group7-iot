#!/bin/bash

API_KEY="YOUR_API_KEY"
SERVER_URL="https://group7-iot.onrender.com"

curl -X POST "$SERVER_URL/api/ingest/session" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-04-28T15:00:00",
    "duration_mins": 25.0,
    "distraction_count": 2,
    "focus_score": 85.0,
    "streak_days": 1,
    "distractions": []
  }'

echo ""