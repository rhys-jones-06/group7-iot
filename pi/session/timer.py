# F5 — Pomodoro Timer + LCD/Joystick UI
# Files: pi/session/timer.py, pi/feedback/display.py
# Timer states: idle → running → break → paused → idle

# Default: 25 min focus / 5 min break, configurable via joystick settings screen
# Buzzer sounds at session/break end
# Break mode disables F2/F3 detection (phone use permitted)
# TODO: Timer state persists across reboots (written to JSON on every state change)

from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum
import json
import threading
from dataclasses import dataclass, asdict, field
import logging
import time
from datetime import datetime, timedelta

from config import TIMER_CONFIG_FILE, DEFAULT_FOCUS_MINS, DEFAULT_BREAK_MINS

if TYPE_CHECKING:
    from state import GlobalState

logger = logging.getLogger(__name__)


import json
from dataclasses import dataclass, asdict, field

@dataclass
class TimerConfig:
    focus_duration: int
    break_duration: int

    def __post_init__(self):
        self._initialized = True


    def save(self):
        with open(TIMER_CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f)

    def __setattr__(self, name, value):
        super().__setattr__(name, value)

        if getattr(self, "_initialized", False):
            if name in ("focus_duration", "break_duration"):
                self.save()


class PomodoroState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    BREAK = "break"
    PAUSED = "paused"

def load_timer_config() -> TimerConfig:
    try:
        with open(TIMER_CONFIG_FILE, "r") as f:
            data = json.load(f)
            return TimerConfig(**data)
    except (FileNotFoundError, json.JSONDecodeError):
        return TimerConfig(
            focus_duration=DEFAULT_FOCUS_MINS,
            break_duration=DEFAULT_BREAK_MINS
        )


class PomodoroTimer:
    def __init__(self, state: GlobalState, lock: threading.RLock) -> None:
        self.state: PomodoroState = PomodoroState.IDLE
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.config: TimerConfig = load_timer_config()
        self._global_state = state
        self._global_lock = lock
        self._paused_remaining: timedelta | None = None
        self._paused_phase: PomodoroState | None = None

    def remaining_seconds(self) -> int:
        if self.state == PomodoroState.PAUSED:
            if self._paused_remaining is not None:
                return max(0, int(self._paused_remaining.total_seconds()))
            return 0

        if self.state in (PomodoroState.RUNNING, PomodoroState.BREAK) and self.end_time is not None:
            return max(0, int((self.end_time - datetime.now()).total_seconds()))
        return 0

    def start_focus(self) -> None:
        self.state = PomodoroState.RUNNING
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(minutes=self.config.focus_duration)

    def start_break(self) -> None:
        self.state = PomodoroState.BREAK
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(minutes=self.config.break_duration)

    def pause(self) -> None:
        if self.state in (PomodoroState.RUNNING, PomodoroState.BREAK):
            self._paused_phase = self.state
            self.state = PomodoroState.PAUSED
            if self.end_time is not None:
                self._paused_remaining = self.end_time - datetime.now()
                self.end_time = None

            with self._global_lock:
                if self._global_state.display:
                    self._global_state.display.tick()

    def resume(self) -> None:
        if self.state == PomodoroState.PAUSED and self._paused_remaining is not None:
            self.end_time = datetime.now() + self._paused_remaining
            self.state = self._paused_phase or PomodoroState.RUNNING
            self._paused_remaining = None
            self._paused_phase = None

    def reset(self) -> None:
        self.state = PomodoroState.IDLE
        self.start_time = None
        self.end_time = None


def timer_thread(state: GlobalState, lock: threading.RLock) -> None:
    while True:
        with lock:
            if not state.running:
                break

            timer = state.timer

            if timer.state == PomodoroState.RUNNING and timer.end_time is not None and datetime.now() >= timer.end_time:
                timer.start_break()

            elif timer.state == PomodoroState.BREAK and timer.end_time is not None and datetime.now() >= timer.end_time:
                timer.reset()

        time.sleep(0.5)
