import threading

import numpy as np

from bilge.voice.idle import IdleUnloadingRecognizer

SPEECH = np.zeros(16_000, dtype=np.float32)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Model:
    made = 0
    closed = 0

    def __init__(self):
        Model.made += 1

    def transcribe(self, samples):
        return "saat kaç"

    def close(self):
        Model.closed += 1


def make(clock):
    Model.made = Model.closed = 0
    return IdleUnloadingRecognizer(Model, idle_seconds=600, clock=clock, check_seconds=3600)


def test_loads_at_once_so_a_broken_model_shows_at_start():
    recognizer = make(Clock())
    assert recognizer.is_loaded and Model.made == 1
    recognizer.close()


def test_lets_the_model_go_after_the_idle_time_and_loads_it_again_when_needed():
    clock = Clock()
    recognizer = make(clock)
    clock.now = 599
    recognizer.unload_if_idle()
    assert recognizer.is_loaded
    clock.now = 601
    recognizer.unload_if_idle()
    assert not recognizer.is_loaded and Model.closed == 1
    assert recognizer.transcribe(SPEECH) == "saat kaç"
    assert recognizer.is_loaded and Model.made == 2
    recognizer.close()


def test_using_it_keeps_it_loaded():
    clock = Clock()
    recognizer = make(clock)
    clock.now = 500
    recognizer.transcribe(SPEECH)
    clock.now = 1000
    recognizer.unload_if_idle()
    assert recognizer.is_loaded
    recognizer.close()


def test_warming_loads_in_the_background():
    clock = Clock()
    recognizer = make(clock)
    clock.now = 700
    recognizer.unload_if_idle()
    recognizer.warm()
    for thread in threading.enumerate():
        if thread.name == "bilge-warm":
            thread.join(2)
    assert recognizer.is_loaded and Model.made == 2
    recognizer.close()
    assert Model.closed == 2
