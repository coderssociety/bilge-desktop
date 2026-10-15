from bilge.voice.audio_io import choose_devices


class FakeSoundDevice:
    class default:
        device = (1, 3)

    def __init__(self, apis):
        self.apis = apis

    def query_hostapis(self, index=None):
        return self.apis if index is None else self.apis[index]

    def query_devices(self, device=None, kind=None):
        return {"index": 7 if device == "Mikrofon (USB)" else device, "hostapi": 0}


def test_windows_prefers_the_wasapi_defaults():
    sd = FakeSoundDevice([{"name": "MME", "default_input_device": 1, "default_output_device": 3},
                          {"name": "Windows WASAPI", "default_input_device": 12, "default_output_device": 10}])  # fmt: skip
    assert choose_devices(sd, None, None) == (12, 10)


def test_other_systems_keep_portaudio_defaults():
    sd = FakeSoundDevice([{"name": "ALSA", "default_input_device": 0, "default_output_device": 0}])
    assert choose_devices(sd, None, None) == (1, 3)


def test_a_device_the_user_chose_wins():
    sd = FakeSoundDevice([{"name": "Windows WASAPI", "default_input_device": 12, "default_output_device": 10}])
    assert choose_devices(sd, "Mikrofon (USB)", None) == (7, 10)
