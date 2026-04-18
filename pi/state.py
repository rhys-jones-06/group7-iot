from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class GlobalState:
    def __init__(self) -> None:
        self.running: bool = True
        self.phone_detected: bool = False
        self.phone_confidence: float = 0.0
        self.latest_frame: NDArray[np.uint8] | None = None
        self.person_head_y: float | None = None
        self.posture_status: str = "starting"
        self.head_drop_pct: float = 0.0
        self.distraction_start: float | None = None
        self.distraction_seconds: float = 0.0
