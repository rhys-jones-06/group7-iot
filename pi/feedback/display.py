# ===========================================================================
# LockIn — pi/feedback/display.py
# CM2211 Group 07 | F5: Grove RGB LCD + Thumb Joystick UI
#
# Joystick mapping:
#   up / down    → cycle menu screens
#   left / right → adjust value (held → auto-repeat after 350 ms)
#   click        → start / pause / resume focus session  (HOME screen only)
#
# Menus, in order:
#   HOME              countdown + state          (click = start / pause)
#   FOCUS_SETTING     focus duration             (left / right ±)
#   BREAK_SETTING     break duration             (left / right ±)
#   ALERT_MODE_SETTING  silent / loud            (left = silent, right = loud)
#
# How the joystick is read robustly:
#
#   Step 1 — classify each poll into exactly ONE zone
#       {neutral, click, left, right, up, down}.
#       Click takes priority (X >= 1000) so it never doubles as "right".
#
#   Step 2 — 2-frame debounce
#       A new zone has to be observed twice in a row before it counts.
#       Single-frame I²C noise spikes vanish.
#
#   Step 3 — fire on transition + hold-to-repeat for directions
#       Click: fires once per press, no auto-repeat.
#       Direction: fires on transition AND every 350 ms while held — so you
#       can fast-scroll values by holding the stick.
#
#   Step 4 — post-click lockout
#       After a click is registered, directional input is ignored for 400 ms
#       so the click-button release (which transiently passes through the
#       "right" zone of the X axis) doesn't fire a phantom right-press.
# ===========================================================================
from __future__ import annotations

import logging
import threading
import time
import traceback
from enum import Enum

import grovepi

from config import DEFAULT_FOCUS_MINS, PIN_JOYSTICK_X, PIN_JOYSTICK_Y
from feedback.grove_rgb_lcd import setRGB, setText
from session.timer import PomodoroState
from state import GlobalState

logger = logging.getLogger(__name__)

grovepi.pinMode(PIN_JOYSTICK_X, "INPUT")
grovepi.pinMode(PIN_JOYSTICK_Y, "INPUT")


# ── joystick zone thresholds (LOOSENED) ────────────────────────────────────
# Idle: X ≈ 513, Y ≈ 511.  Full deflection: ~250 (down/left) and ~770 (up/right).
# Click pulls X to ~1023.  The wide neutral band (350..700 each axis) absorbs
# both quiescent noise and modest mis-pushes; the tightened click threshold
# (>= 1000) leaves a safe gap above the maximum directional reading.
_CLICK_X_MIN  = 1000
_LEFT_X_MAX   = 350
_RIGHT_X_MIN  = 700
_UP_Y_MAX     = 350
_DOWN_Y_MIN   = 700

_REPEAT_COOLDOWN_S      = 0.35    # min interval between repeated direction fires
_POST_CLICK_LOCKOUT_S   = 0.40    # ignore direction zones for this long after a click

# Adjustable focus / break minute range
_MIN_DURATION_MIN = 1
_MAX_DURATION_MIN = 60


def _step_decrease(cur: int) -> int:
    """5-min steps above 10, 1-min steps below — finer control near the minimum."""
    if cur > 10: return cur - 5
    if cur > _MIN_DURATION_MIN: return cur - 1
    return _MIN_DURATION_MIN


def _step_increase(cur: int) -> int:
    """1-min steps below 10, 5-min steps above — fast traversal of normal Pomodoro values."""
    if cur < 10: return cur + 1
    return min(_MAX_DURATION_MIN, cur + 5)


class Menu(Enum):
    HOME  = "home"
    STATS = "stats"


class Display:
    MENU_ORDER = [Menu.HOME, Menu.STATS]

    def __init__(self, global_state: GlobalState, state_lock: threading.RLock) -> None:
        setRGB(50, 50, 50)
        time.sleep(0.5)

        self._state      = global_state
        self._state_lock = state_lock

        # Joystick debounce state
        self._pending_zone:        str   = "neutral"
        self._current_zone:        str   = "neutral"
        self._last_action_t:       float = 0.0
        self._post_click_until:    float = 0.0     # monotonic timestamp

        self._current_menu = Menu.HOME
        self.change_screen(Menu.HOME)

    # ── joystick polling ─────────────────────────────────────────────────────
    @staticmethod
    def _classify(x: int, y: int) -> str:
        if x >= _CLICK_X_MIN: return "click"
        if x <  _LEFT_X_MAX:  return "left"
        if x >  _RIGHT_X_MIN: return "right"
        if y <  _UP_Y_MAX:    return "up"
        if y >  _DOWN_Y_MIN:  return "down"
        return "neutral"

    def handle_joystick_input(self) -> None:
        try:
            x = grovepi.analogRead(PIN_JOYSTICK_X)
            y = grovepi.analogRead(PIN_JOYSTICK_Y)
        except Exception:
            return    # transient I²C errors — skip this poll

        new_zone = self._classify(x, y)

        # ── debounce: zone must repeat to be confirmed ──────────────────────
        if new_zone == self._pending_zone:
            confirmed = new_zone
        else:
            self._pending_zone = new_zone
            confirmed = self._current_zone

        prev_zone = self._current_zone
        self._current_zone = confirmed

        if confirmed == "neutral":
            return

        now = time.monotonic()
        is_transition = (confirmed != prev_zone)

        if confirmed == "click":
            if is_transition:
                self._handle_click()
                self._last_action_t    = now
                self._post_click_until = now + _POST_CLICK_LOCKOUT_S
            return

        # direction zone — but block during post-click lockout so click-release
        # can't fire a phantom direction press
        if now < self._post_click_until:
            return

        if is_transition or (now - self._last_action_t) >= _REPEAT_COOLDOWN_S:
            handler = {
                "left":  self._handle_left,
                "right": self._handle_right,
                "up":    self._handle_up,
                "down":  self._handle_down,
            }[confirmed]
            handler()
            self._last_action_t = now

    # ── input handlers ───────────────────────────────────────────────────────
    def _handle_click(self) -> None:
        if self._current_menu == Menu.HOME:
            with self._state_lock:
                t = self._state.timer
                if t.state == PomodoroState.IDLE:
                    t.reset()
                    t.start_focus()
                elif t.state in (PomodoroState.RUNNING, PomodoroState.BREAK):
                    t.pause()
                elif t.state == PomodoroState.PAUSED:
                    t.resume()
            self.tick()

    def _handle_up(self) -> None:
        idx = self.MENU_ORDER.index(self._current_menu)
        self.change_screen(self.MENU_ORDER[(idx - 1) % len(self.MENU_ORDER)])

    def _handle_down(self) -> None:
        idx = self.MENU_ORDER.index(self._current_menu)
        self.change_screen(self.MENU_ORDER[(idx + 1) % len(self.MENU_ORDER)])

    def _handle_left(self) -> None:
        pass

    def _handle_right(self) -> None:
        pass

    # ── rendering ────────────────────────────────────────────────────────────
    def change_screen(self, screen: Menu) -> None:
        self._current_menu = screen
        self.tick()

    def _display_home(self) -> None:
        with self._state_lock:
            t        = self._state.timer
            state    = t.state
            remaining = t.remaining_seconds()

        minutes = int(remaining) // 60
        seconds = int(remaining) % 60
        try:
            if state == PomodoroState.IDLE:
                setText("idle\nClick to start")
            elif state == PomodoroState.PAUSED:
                setText(f"paused; phone OK\n{minutes:02d}:{seconds:02d}")
            else:
                setText(f"{state.value}\n{minutes:02d}:{seconds:02d}")
        except Exception:
            print("LCD ERROR")
            traceback.print_exc()

    def _display_stats(self) -> None:
        with self._state_lock:
            distractions = self._state.session_distraction_count
            posture      = self._state.posture_status
            timer_state  = self._state.timer.state if self._state.timer else None

        if timer_state == PomodoroState.RUNNING:
            focus_score = max(0, 100 - distractions * 10)
            setText(f"Distracts: {distractions}\nScore: {focus_score}%")
        else:
            setText(f"Posture: {posture[:7]}\nDistracts: {distractions}")

    def tick(self) -> None:
        if   self._current_menu == Menu.HOME:  self._display_home()
        elif self._current_menu == Menu.STATS: self._display_stats()


# ─── thread entry point ─────────────────────────────────────────────────────

def menu_handling_thread(state: GlobalState, lock: threading.RLock) -> None:
    display = Display(state, lock)

    with lock:
        state.display = display

    while True:
        # poll joystick 10× then re-render the home screen if a session is active
        for _ in range(10):
            display.handle_joystick_input()
            time.sleep(0.05)             # 50 ms × 10 = 500 ms per outer cycle

        with lock:
            if not state.running:
                try:
                    setText("")
                    setRGB(0, 0, 0)
                except Exception:
                    pass
                break
            should_tick = bool(
                state.timer
                and state.timer.state in (PomodoroState.RUNNING, PomodoroState.BREAK)
            )

        # tick OUTSIDE the lock — _display_home re-acquires it
        if should_tick:
            display.tick()
