import pytest

from bilge.desktop.base import MediaCommand, VolumeState
from bilge.desktop.linux.audio import LinuxVolume
from bilge.desktop.linux.media import MprisMedia, NoPlayer
from bilge.desktop.process import Completed, DesktopError, MissingProgram

from .fakes import FakeRunner


def test_pipewire_volume_is_read_and_set_without_going_past_100():
    runner = FakeRunner({"wpctl", "pactl"}, {"wpctl get-volume": "Volume: 0.42 [MUTED]\n"})
    volume = LinuxVolume(runner)
    assert volume.state() == VolumeState(42, True)
    volume.set_level(130)
    assert runner.commands[-2:] == [
        ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"],
        ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "100%"],
    ]


def test_pulseaudio_volume_is_read_from_pactl():
    runner = FakeRunner(
        {"pactl"},
        {
            "pactl get-sink-volume": "Volume: front-left: 26214 /  40% / -23.88 dB,   front-right: 26214 /  40%",
            "pactl get-sink-mute": "Mute: no",
        },
    )
    assert LinuxVolume(runner).state() == VolumeState(40, False)


def test_alsa_is_the_last_resort():
    runner = FakeRunner({"amixer"}, {"amixer sget Master": "Front Left: Playback 26 [40%] [-30.00dB] [off]"})
    volume = LinuxVolume(runner)
    assert volume.state() == VolumeState(40, True)
    volume.set_muted(False)
    assert runner.commands[-1] == ["amixer", "-q", "sset", "Master", "unmute"]


def test_no_sound_tool_names_what_to_install():
    with pytest.raises(MissingProgram) as error:
        LinuxVolume(FakeRunner()).state()
    assert error.value.programs == ("wpctl", "pactl", "amixer")


def test_unreadable_volume_is_an_error():
    runner = FakeRunner({"wpctl"}, {"wpctl get-volume": Completed(0, "nonsense", "")})
    with pytest.raises(DesktopError):
        LinuxVolume(runner).state()


class FakeBus:
    def __init__(self, players):
        # name -> {"PlaybackStatus": ..., "Metadata": ..., "Identity": ...}
        self.players = players
        self.calls = []

    def names(self):
        return ["org.freedesktop.DBus", *self.players]

    def call(self, name, path, interface, method, signature=None, *args):
        self.calls.append((name, method))
        return ()

    def get(self, name, path, interface, prop):
        value = self.players[name].get(prop)
        if value is None:
            raise DesktopError("no such property")
        return value


def test_the_playing_player_is_the_one_controlled():
    bus = FakeBus({
        "org.mpris.MediaPlayer2.vlc": {"PlaybackStatus": "Paused", "Identity": "VLC media player"},
        "org.mpris.MediaPlayer2.spotify": {
            "PlaybackStatus": "Playing", "Identity": "Spotify",
            "Metadata": {"xesam:title": ("s", "Gesi Bağları"), "xesam:artist": ("as", ["Zeki Müren"])},
        },
    })  # fmt: skip
    media = MprisMedia(bus)
    playing = media.now_playing()
    assert (playing.player, playing.playing, playing.title, playing.artist) == (
        "Spotify", True, "Gesi Bağları", "Zeki Müren",
    )  # fmt: skip
    assert media.send(MediaCommand.NEXT) == "Spotify"
    assert bus.calls == [("org.mpris.MediaPlayer2.spotify", "Next")]


def test_a_player_without_identity_is_named_from_its_bus_name():
    bus = FakeBus({"org.mpris.MediaPlayer2.rhythmbox": {"PlaybackStatus": "Stopped"}})
    assert MprisMedia(bus).send(MediaCommand.PLAY) == "Rhythmbox"


def test_no_player_open():
    media = MprisMedia(FakeBus({}))
    assert media.now_playing() is None
    with pytest.raises(NoPlayer):
        media.send(MediaCommand.PAUSE)
