from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from session.timer import PomodoroTimer

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from feedback.display import Display


class GlobalState:
    def __init__(self, lock: threading.RLock) -> None:
        self.running: bool = True
        self.phone_detected: bool = False
        self.phone_confidence: float = 0.0
        self.latest_frame: NDArray[np.uint8] | None = None
        self.person_head_y: float | None = None
        self.posture_status: str = "starting"
        self.head_drop_pct: float = 0.0
        self.distraction_start: float | None = None
        self.distraction_seconds: float = 0.0
        self.low_light: bool = False
        self.timer: PomodoroTimer = PomodoroTimer(self, lock)
        self.display: Display | None = None
