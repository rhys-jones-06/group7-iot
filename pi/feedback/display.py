# ===========================================================================
# LockIn — pi/feedback/display.py
# CM2211 Group 07 | F5: Grove RGB LCD countdown display
#
# Runs as a daemon thread started from main.py. Reads shared_state every
# second and updates the Grove RGB LCD with the current session state.
#
# LCD layout (16 chars per line):
#   Line 1:  "<STATE>     MM:SS"   e.g. "FOCUS      24:32"
#   Line 2:  "Distr: N         "   e.g. "Distr: 3        "
#
# Backlight colour:
#   Green  — focused, no active distraction
#   Red    — currently distracted
#   Orange — paused (no person at desk)
#   Blue   — break time
#   White  — calibrating / idle
# ===========================================================================

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

try:
    sys.path.insert(0, os.path.dirname(__file__))
    from grove_rgb_lcd import setRGB, setText_norefresh
    LCD_AVAILABLE = True
except Exception:
    LCD_AVAILABLE = False


def _fmt_time(secs: int) -> str:
    m, s = divmod(max(0, secs), 60)
    return f'{m:02d}:{s:02d}'


def start_lcd_display(shared_state: dict, state_lock) -> None:
    """F5: background thread — keep LCD in sync with session state."""
    if not LCD_AVAILABLE:
        logger.warning('[lcd] Grove RGB LCD not available — F5 display disabled')
        return

    logger.info('[lcd] Display thread started (F5)')
    last_text = ''
    last_rgb  = (-1, -1, -1)

    while True:
        with state_lock:
            if not shared_state.get('running', True):
                break
            state        = shared_state.get('session_state', 'idle')
            remaining    = shared_state.get('session_remaining_secs', 0)
            distractions = shared_state.get('session_distractions', 0)
            distracted   = shared_state.get('is_distracted', False)
            posture_st   = shared_state.get('posture_status', 'starting')

        if state == 'focus':
            label = 'FOCUS'
            rgb   = (220, 20, 20) if distracted else (0, 190, 50)
            line2 = f'Distr: {distractions}'
        elif state == 'paused':
            label = 'PAUSED'
            rgb   = (200, 100, 0)
            line2 = 'Away from desk'
        elif state == 'break':
            label = 'BREAK'
            rgb   = (0, 70, 200)
            line2 = 'Phone OK  :)'
        elif posture_st in ('starting', 'calibrating'):
            label = 'CALIBRATING'
            rgb   = (180, 180, 180)
            line2 = 'Sit upright...'
        else:
            label = 'LOCKIN'
            rgb   = (60, 60, 60)
            line2 = 'Ready'

        time_str = _fmt_time(remaining)
        line1    = f'{label:<10}{time_str}'
        text     = f'{line1}\n{line2}'

        try:
            if rgb != last_rgb:
                setRGB(*rgb)
                last_rgb = rgb
            if text != last_text:
                setText_norefresh(text)
                last_text = text
        except Exception as e:
            logger.warning(f'[lcd] Write error: {e}')
            last_text = ''  # force retry next tick

        time.sleep(1.0)

    try:
        setText_norefresh('LockIn stopped  ')
        setRGB(0, 0, 0)
    except Exception:
        pass
    logger.info('[lcd] Display thread stopped')


# ── Joystick test (run directly to verify hardware) ────────────────────────────
if __name__ == '__main__':
    import grovepi
    from grove_rgb_lcd import setRGB, setText

    PIN_X = 0
    PIN_Y = 1
    grovepi.pinMode(PIN_X, "INPUT")
    grovepi.pinMode(PIN_Y, "INPUT")

    setRGB(50, 50, 50)
    setText("Hello LockIn")

    while True:
        x     = grovepi.analogRead(PIN_X)
        y     = grovepi.analogRead(PIN_Y)
        click = 1 if x >= 1020 else 0
        print(f"x={x}  y={y}  click={click}")
        time.sleep(0.5)
