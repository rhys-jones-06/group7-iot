from __future__ import annotations

from enum import Enum
import threading
import time
import traceback
import logging

import grovepi

from feedback.grove_rgb_lcd import setRGB, setText
from hardware import i2c_lock
from config import DEFAULT_FOCUS_MINS
from session.timer import PomodoroState
from state import GlobalState

logger = logging.getLogger(__name__)

# The Grove Thumb Joystick is an analog device that outputs analog signal ranging from 0 to 1023
# The X and Y axes are two ~10k potentiometers and a momentary push button which shorts the x axis

PIN_JOYSTICK_X = 0
PIN_JOYSTICK_Y = 1

with i2c_lock:
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


# F5 — Pomodoro Timer + LCD/Joystick UI
# Files: pi/session/timer.py, pi/feedback/display.py
# Timer states: idle → running → break → paused → idle

# Default: 25 min focus / 5 min break, configurable via joystick settings screen
# Buzzer sounds at session/break end
# Break mode disables F2/F3 detection (phone use permitted)
# Timer state persists across reboots (written to JSON on every state change)

# LCD screens (joystick up/down to navigate, left/right to adjust, press to confirm):

# Screen     Displays
# Home       Countdown timer, current state (FOCUS / BREAK / IDLE)
# Stats      Today's session count, distraction count
# Streak     Current streak in days
# Settings   Focus duration, break duration, alert sensitivity, mantra text
# Break      Break countdown, "Phone OK" message

class Menu(Enum):
    HOME = "home"
    # STATS = "stats"
    # STREAK = "streak"
    FOCUS_SETTING = "focus_setting"
    BREAK_SETTING = "break_setting"


class Display:
    MENU_ORDER = [Menu.HOME, Menu.FOCUS_SETTING, Menu.BREAK_SETTING]

    def __init__(self, global_state: GlobalState, state_lock: threading.RLock) -> None:
        setRGB(50, 50, 50)
        time.sleep(0.5)

        self._state = global_state
        self._state_lock = state_lock

        self._clicked = False
        self._handled_movement = None

        self._current_menu = Menu.HOME
        self.change_screen(Menu.HOME)

    def handle_joystick_input(self) -> None:
        try:
            with i2c_lock:
                x = grovepi.analogRead(PIN_JOYSTICK_X)
                y = grovepi.analogRead(PIN_JOYSTICK_Y)
        except Exception:
            print("JOYSTICK ERROR")
            traceback.print_exc()
            return

        click = x >= 1020

        if click and not self._clicked:
            self._handle_click()
        self._clicked = click

        if x < 300:
            if self._handled_movement != "left":
                self._handle_left()
            self._handled_movement = "left"
        elif x > 700:
            if self._handled_movement != "right":
                self._handle_right()
            self._handled_movement = "right"
        elif y < 300:
            if self._handled_movement != "up":
                self._handle_up()
            self._handled_movement = "up"
        elif y > 700:
            if self._handled_movement != "down":
                self._handle_down()
            self._handled_movement = "down"
        else:
            self._handled_movement = None

    def _handle_click(self) -> None:
        if self._current_menu == Menu.HOME:
            with self._state_lock:
                if self._state.timer.state == PomodoroState.IDLE:
                    self._state.timer.reset()
                    self._state.timer.start_focus()
                elif self._state.timer.state in (PomodoroState.RUNNING, PomodoroState.BREAK):
                    self._state.timer.pause()
                elif self._state.timer.state == PomodoroState.PAUSED:
                    self._state.timer.resume()

    def _handle_up(self) -> None:
        current_index = self.MENU_ORDER.index(self._current_menu)
        new_index = (current_index - 1) % len(self.MENU_ORDER)
        self.change_screen(self.MENU_ORDER[new_index])

    def _handle_down(self) -> None:
        current_index = self.MENU_ORDER.index(self._current_menu)
        new_index = (current_index + 1) % len(self.MENU_ORDER)
        self.change_screen(self.MENU_ORDER[new_index])

    def _handle_left(self) -> None:
        if self._current_menu == Menu.FOCUS_SETTING:
            with self._state_lock:
                current = self._state.timer.config.focus_duration
                new_duration = max(5, current - 5)
                self._state.timer.config.focus_duration = new_duration
                self.tick()
        elif self._current_menu == Menu.BREAK_SETTING:
            with self._state_lock:
                current = self._state.timer.config.break_duration
                new_duration = max(5, current - 5)
                self._state.timer.config.break_duration = new_duration
                self.tick()

    def _handle_right(self) -> None:
        if self._current_menu == Menu.FOCUS_SETTING:
            with self._state_lock:
                current = self._state.timer.config.focus_duration
                new_duration = min(60, current + 5)
                self._state.timer.config.focus_duration = new_duration
                self.tick()
        elif self._current_menu == Menu.BREAK_SETTING:
            with self._state_lock:
                current = self._state.timer.config.break_duration
                new_duration = min(60, current + 5)
                self._state.timer.config.break_duration = new_duration
                self.tick()

    def change_screen(self, screen: Menu) -> None:
        self._current_menu = screen
        if screen == Menu.HOME:
            self._display_home()
        elif screen == Menu.FOCUS_SETTING:
            self._display_focus_setting()
        elif screen == Menu.BREAK_SETTING:
            self._display_break_setting()

    def _display_home(self) -> None:
        with self._state_lock:
            state = self._state.timer.state
            remaining = self._state.timer.remaining_seconds()

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

    def _display_focus_setting(self) -> None:
        current_duration = self._state.timer.config.focus_duration if self._state.timer else DEFAULT_FOCUS_MINS
        setText(f"Focus time <- ->\n{current_duration} min")

    def _display_break_setting(self) -> None:
        current_duration = self._state.timer.config.break_duration if self._state.timer else DEFAULT_FOCUS_MINS
        setText(f"Break time <- ->\n{current_duration} min")


    def tick(self) -> None:
        if self._current_menu == Menu.HOME:
            self._display_home()
        elif self._current_menu == Menu.FOCUS_SETTING:
            self._display_focus_setting()
        elif self._current_menu == Menu.BREAK_SETTING:
            self._display_break_setting()


def menu_handling_thread(state: GlobalState, lock: threading.RLock) -> None:
    display = Display(state, lock)

    with lock:
        state.display = display

    while True:
        for _ in range(10):
            display.handle_joystick_input()
            time.sleep(0.03)

        with lock:
            if not state.running:
                setText("")
                setRGB(0, 0, 0)
                break

            should_tick = bool(
                state.timer and state.timer.state in (PomodoroState.RUNNING, PomodoroState.BREAK)
            )

        # Call tick outside the lock to avoid deadlocking on nested lock acquisition in _display_home.
        if should_tick:
            display.tick()
