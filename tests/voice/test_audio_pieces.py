import numpy as np

from bilge.voice.audio_io import CHUNK, FrontEnd, PlaybackBuffer
from bilge.voice.echo import EchoCanceller


def test_playback_buffer_plays_clips_in_order_and_pads_with_silence():
    buffer = PlaybackBuffer()
    buffer.add(np.ones(3, dtype=np.float32))
    buffer.add(np.full(2, 2, dtype=np.float32))
    assert buffer.take(4).tolist() == [1, 1, 1, 2]
    assert buffer.is_playing
    assert buffer.take(3).tolist() == [2, 0, 0]
    assert not buffer.is_playing


def test_clearing_stops_playback_at_once():
    buffer = PlaybackBuffer()
    buffer.add(np.ones(100, dtype=np.float32))
    buffer.clear()
    assert buffer.take(10).tolist() == [0] * 10


class OneShotDevice:
    sample_rate = 48_000

    def __init__(self, seconds):
        self.mic = (np.sin(np.arange(int(seconds * self.sample_rate)) / 20) * 0.3).astype(np.float32)

    def start(self, on_block):
        for i in range(0, len(self.mic), 480):
            on_block(self.mic[i : i + 480], np.zeros(480, dtype=np.float32))

    def stop(self):
        pass


def test_front_end_delivers_16_khz_chunks_of_512():
    chunks = []
    front = FrontEnd(OneShotDevice(2.0), chunks.append, echo=None)
    front.start()
    front.stop()
    assert chunks and all(c.shape == (CHUNK,) and c.dtype == np.float32 for c in chunks)
    assert abs(len(chunks) * CHUNK - 32_000) < 2 * CHUNK


def test_echo_canceller_removes_most_of_a_delayed_echo():
    rng = np.random.default_rng(0)
    far = (rng.standard_normal(16_000 * 4) * 0.2).astype(np.float32)
    delay = 800
    mic = np.concatenate([np.zeros(delay, np.float32), far[:-delay]]) * 0.5
    echo = EchoCanceller()
    out = np.concatenate([echo.process(mic[i : i + 512], far[i : i + 512]) for i in range(0, len(far), 512)])
    tail = slice(16_000 * 2, len(out))
    reduction = 10 * np.log10(np.mean(mic[tail] ** 2) / max(np.mean(out[tail] ** 2), 1e-12))
    assert reduction > 15
