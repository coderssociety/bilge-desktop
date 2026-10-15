"""Music and video players through MPRIS, the D-Bus interface Spotify, Rhythmbox, VLC, browsers and others share."""

from bilge.desktop.base import MediaCommand, NowPlaying
from bilge.desktop.linux.dbus import Bus
from bilge.desktop.process import DesktopError

_PREFIX = "org.mpris.MediaPlayer2."
_PATH = "/org/mpris/MediaPlayer2"
_ROOT = "org.mpris.MediaPlayer2"
_PLAYER = "org.mpris.MediaPlayer2.Player"
_METHODS = {
    MediaCommand.PLAY: "Play",
    MediaCommand.PAUSE: "Pause",
    MediaCommand.TOGGLE: "PlayPause",
    MediaCommand.NEXT: "Next",
    MediaCommand.PREVIOUS: "Previous",
}
# The player the user most likely means: the one playing, then one paused mid-track.
_PREFERENCE = {"Playing": 0, "Paused": 1}


class NoPlayer(DesktopError):
    pass


class MprisMedia:
    def __init__(self, bus: Bus):
        self._bus = bus

    def now_playing(self) -> NowPlaying | None:
        player = self._choose()
        if player is None:
            return None
        name, status = player
        metadata = self._optional(name, _PLAYER, "Metadata") or {}
        title = _text(metadata.get("xesam:title"))
        artists = _value(metadata.get("xesam:artist"))
        artist = ", ".join(artists) if isinstance(artists, list) else _text(metadata.get("xesam:artist"))
        return NowPlaying(self._identity(name), status == "Playing", title, artist)

    def send(self, command: MediaCommand) -> str:
        player = self._choose()
        if player is None:
            raise NoPlayer("No MPRIS player is running")
        name, _ = player
        self._bus.call(name, _PATH, _PLAYER, _METHODS[command])
        return self._identity(name)

    def _choose(self) -> tuple[str, str] | None:
        players = [name for name in self._bus.names() if name.startswith(_PREFIX)]
        if not players:
            return None
        statuses = [(name, str(self._optional(name, _PLAYER, "PlaybackStatus") or "")) for name in players]
        return min(statuses, key=lambda item: _PREFERENCE.get(item[1], 2))

    def _identity(self, name: str) -> str:
        identity = self._optional(name, _ROOT, "Identity")
        if identity:
            return str(identity)
        # "org.mpris.MediaPlayer2.spotify" or "…chromium.instance1234".
        return name.removeprefix(_PREFIX).split(".")[0].capitalize()

    def _optional(self, name: str, interface: str, prop: str):
        """Players implement the optional properties unevenly; a missing one is not an error."""
        try:
            return self._bus.get(name, _PATH, interface, prop)
        except DesktopError:
            return None


def _value(variant):
    """Metadata values are variants, (signature, value)."""
    if isinstance(variant, tuple) and len(variant) == 2:
        return variant[1]
    return variant


def _text(variant) -> str:
    value = _value(variant)
    return str(value) if value else ""
