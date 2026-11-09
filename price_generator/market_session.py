"""Illustrative US equity session, expressed in Eastern market time.

This models one typical day, not a dated exchange calendar. Coefficients are
scenario parameters rather than empirical estimates for a particular stock.
"""

from dataclasses import dataclass
import math


OPEN_SECONDS = 9 * 3600 + 30 * 60
CLOSE_SECONDS = 16 * 3600
PRESETS = {
    "pre_open": OPEN_SECONDS - 300,
    "opening": OPEN_SECONDS,
    "midday": 12 * 3600,
    "closing": CLOSE_SECONDS - 1800,
    "final_minute": CLOSE_SECONDS - 60,
}
BOUNDARIES = (OPEN_SECONDS, 10 * 3600, 11 * 3600 + 1800,
              14 * 3600 + 1800, CLOSE_SECONDS - 1800, CLOSE_SECONDS)
PHASE_LABELS = {
    "pre_open": "Pre-open", "opening": "Opening discovery", "regular": "Regular trading",
    "midday": "Midday", "closing": "Closing run-up", "closed": "Market closed",
}


@dataclass(frozen=True)
class SessionConditions:
    phase: str
    volatility: float
    volume: float
    spread: float
    depth: float
    refresh_seconds: float
    imbalance: float


@dataclass(frozen=True)
class USStockSession:
    preset: str = "opening"
    playback_speed: float = 20.0

    def __post_init__(self) -> None:
        if not isinstance(self.preset, str) or self.preset not in PRESETS:
            raise ValueError("Choose a supported US stock session preset")
        speed = self.playback_speed
        if (isinstance(speed, bool) or not isinstance(speed, (int, float))
                or not 1 <= speed <= 600):
            raise ValueError("playback_speed must be a number between 1 and 600")

    @property
    def start_seconds(self) -> int:
        return PRESETS[self.preset]

    @property
    def duration_seconds(self) -> int:
        return CLOSE_SECONDS - self.start_seconds

    def seconds_of_day(self, elapsed: float) -> float:
        return min(CLOSE_SECONDS, self.start_seconds + max(0, elapsed))

    def seconds_to_boundary(self, elapsed: float) -> float:
        now = self.seconds_of_day(elapsed)
        return next((boundary - now for boundary in BOUNDARIES if boundary > now + 1e-9), math.inf)

    def conditions(self, elapsed: float, pressure: float) -> SessionConditions:
        now = self.seconds_of_day(elapsed)
        if now >= CLOSE_SECONDS:
            return SessionConditions("closed", 0, 0, .7, 2.2, 2, pressure)
        if now < OPEN_SECONDS:
            return SessionConditions("pre_open", 0, 0, 4, .35, 20, pressure)
        if now < 10 * 3600:
            pulse = math.exp(-(now - OPEN_SECONDS) / 600)
            return SessionConditions("opening", 1 + 1.8 * pulse, 1 + 2.5 * pulse,
                                     1 + 2.5 * pulse, 1 - .45 * pulse, 2,
                                     pressure * (.3 + .7 * pulse))
        if now >= CLOSE_SECONDS - 1800:
            urgency = (now - (CLOSE_SECONDS - 1800)) / 1800
            return SessionConditions("closing", 1 + .6 * urgency, 1.5 + 3.5 * urgency,
                                     .95 - .25 * urgency, 1.2 + urgency, 2,
                                     pressure * (.5 + .5 * urgency))
        if 11 * 3600 + 1800 <= now < 14 * 3600 + 1800:
            return SessionConditions("midday", .8, .7, 1, 1, 10, pressure * .2)
        return SessionConditions("regular", 1, 1, 1, 1, 8, pressure * .3)
