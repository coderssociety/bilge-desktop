"""The default speaker's volume (Core Audio through pycaw) and the playing media (the media controls Windows shows
over the volume flyout, which Spotify, browsers and most players report to)."""

import asyncio

from bilge.desktop.base import MediaCommand, NowPlaying, VolumeState
from bilge.desktop.process import DesktopError, MissingProgram
from bilge.desktop.windows import com


def _endpoint():
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError as error:
        raise MissingProgram("pycaw") from error
    speakers = AudioUtilities.GetSpeakers()
    if speakers is None:
        raise DesktopError("No speaker")
    volume = getattr(speakers, "EndpointVolume", None)
    if volume is not None:
        return volume
    # pycaw before 2024 hands back the raw device.
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume

    return cast(speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))


class WindowsVolume:
    def _call(self, action):
        try:
            return com.call(_endpoint, action, keep=(DesktopError,))
        except com.ComFailure as error:
            # No sound output device, or the audio service stopped.
            raise DesktopError(f"Core Audio: {error}") from None

    def state(self) -> VolumeState:
        return self._call(lambda volume: VolumeState(round(volume.GetMasterVolumeLevelScalar() * 100),
                                                     bool(volume.GetMute())))  # fmt: skip

    def set_level(self, level: int) -> None:
        def change(volume) -> None:
            volume.SetMute(0, None)
            volume.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)

        self._call(change)

    def set_muted(self, muted: bool) -> None:
        self._call(lambda volume: volume.SetMute(1 if muted else 0, None))


_PLAYING = 4
_METHODS = {
    MediaCommand.PLAY: "try_play_async",
    MediaCommand.PAUSE: "try_pause_async",
    MediaCommand.TOGGLE: "try_toggle_play_pause_async",
    MediaCommand.NEXT: "try_skip_next_async",
    MediaCommand.PREVIOUS: "try_skip_previous_async",
}


def player_name(app_id: str) -> str:
    """ "Spotify.exe" → "Spotify"; "Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic" → "ZuneMusic";
    "MSEdge" → "MSEdge"."""
    name = app_id.split("!", 1)[-1].rsplit("\\", 1)[-1]
    name = name.removesuffix(".exe").removesuffix(".EXE")
    return name.rsplit(".", 1)[-1] if "." in name else name


class WindowsMedia:
    def __init__(self, sessions=None):
        # For tests: a function returning the media sessions.
        self._sessions = sessions

    async def _all(self) -> list:
        if self._sessions is not None:
            return list(self._sessions())
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        except ImportError as error:
            raise MissingProgram("winrt-Windows.Media.Control") from error
        manager = await Manager.request_async()
        return list(manager.get_sessions())

    async def _choose(self):
        sessions = await self._all()
        playing = [s for s in sessions if int(s.get_playback_info().playback_status) == _PLAYING]
        return (playing or sessions or [None])[0]

    def _run(self, coroutine):
        try:
            return asyncio.run(coroutine)
        except OSError as error:
            raise DesktopError(f"Media controls: {error}") from error

    def now_playing(self) -> NowPlaying | None:
        async def read() -> NowPlaying | None:
            session = await self._choose()
            if session is None:
                return None
            properties = await session.try_get_media_properties_async()
            playing = int(session.get_playback_info().playback_status) == _PLAYING
            return NowPlaying(player_name(session.source_app_user_model_id), playing, properties.title or "",
                              properties.artist or "")  # fmt: skip

        return self._run(read())

    def send(self, command: MediaCommand) -> str:
        async def act() -> str:
            session = await self._choose()
            if session is None:
                raise DesktopError("No media session")
            if not await getattr(session, _METHODS[command])():
                raise DesktopError(f"The player refused {command}")
            return player_name(session.source_app_user_model_id)

        return self._run(act())
