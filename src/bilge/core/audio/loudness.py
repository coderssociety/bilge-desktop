"""Whether a recording holds anything loud enough to be speech, judged against its own background.

Speech detection lets through some breaths, rustles and steady machine noise, and Whisper writes a sentence for
them anyway. Speech rises well above the noise between words, so a recording is kept only if part of it, long enough
for a syllable, stands out from the quietest part of the same recording. Measuring against the recording's own floor
makes a fan's steady hum, however loud, count as background.
"""

import math
from collections.abc import Sequence

FRAME_SECONDS = 0.02
# How far above the recording's own floor speech rises, and for how long at least.
RISE_DB = 10.0
MIN_LOUD_SECONDS = 0.15
# Below this even the loudest part is near the microphone's own noise (dBFS).
SILENT_PEAK_DB = -55.0
# The floor is the level of the quietest tenth of the frames; the peak, of the loudest twentieth.
_FLOOR_PERCENTILE = 0.1
_PEAK_PERCENTILE = 0.95
_DB_OF_ZERO = -120.0


def frame_levels(samples: Sequence[float], sample_rate: int) -> list[float]:
    """The level of each 20 ms frame in dBFS (the audio code computes the same with numpy)."""
    size = max(1, int(sample_rate * FRAME_SECONDS))
    levels = []
    for start in range(0, len(samples) - size + 1, size):
        frame = samples[start : start + size]
        levels.append(level_of_power(sum(value * value for value in frame) / size))
    return levels


def level_of_power(power: float) -> float:
    return 10 * math.log10(power) if power > 0 else _DB_OF_ZERO


def _percentile(ordered: list[float], fraction: float) -> float:
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def holds_speech(levels: Sequence[float]) -> bool:
    """`levels`: the recording's 20 ms frame levels, from `frame_levels`."""
    if not levels:
        return False
    ordered = sorted(levels)
    if _percentile(ordered, _PEAK_PERCENTILE) < SILENT_PEAK_DB:
        return False
    floor = _percentile(ordered, _FLOOR_PERCENTILE)
    loud = sum(1 for level in levels if level >= floor + RISE_DB)
    return loud * FRAME_SECONDS >= MIN_LOUD_SECONDS
