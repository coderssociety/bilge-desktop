import math
import random

from bilge.core.audio.loudness import frame_levels, holds_speech

RATE = 16_000


def noise(seconds: float, amplitude: float, seed: int = 1) -> list[float]:
    generator = random.Random(seed)
    return [generator.uniform(-amplitude, amplitude) for _ in range(int(seconds * RATE))]


def tone(seconds: float, amplitude: float) -> list[float]:
    return [amplitude * math.sin(2 * math.pi * 220 * i / RATE) for i in range(int(seconds * RATE))]


def mixed(*parts: list[float]) -> list[float]:
    return [sample for part in parts for sample in part]


def judged(samples: list[float]) -> bool:
    return holds_speech(frame_levels(samples, RATE))


def test_a_voice_over_room_noise_is_kept() -> None:
    background = 0.002
    voice = [a + b for a, b in zip(tone(0.8, 0.1), noise(0.8, background, seed=2), strict=True)]
    assert judged(mixed(noise(0.5, background), voice, noise(0.6, background, seed=3)))


def test_a_quiet_voice_is_kept_when_the_room_is_quieter() -> None:
    # About -40 dBFS at its loudest: a laptop microphone across the room.
    assert judged(mixed(noise(0.5, 0.0005), tone(0.6, 0.014), noise(0.5, 0.0005, seed=4)))


def test_steady_noise_is_dropped_however_loud() -> None:
    assert not judged(noise(2.0, 0.3))


def test_near_silence_is_dropped() -> None:
    assert not judged(mixed(noise(0.5, 0.0001), tone(0.6, 0.0015), noise(0.5, 0.0001, seed=5)))


def test_a_click_is_too_short_to_be_speech() -> None:
    assert not judged(mixed(noise(0.6, 0.001), tone(0.1, 0.3), noise(0.6, 0.001, seed=6)))


def test_nothing_is_not_speech() -> None:
    assert not judged([])
    assert not judged([0.0] * RATE)
