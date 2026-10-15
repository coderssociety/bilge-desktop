"""Volume and the music player."""

from enum import StrEnum
from typing import Any

from bilge.core.language import AssistantLanguage
from bilge.desktop.base import Media, MediaCommand, Volume
from bilge.desktop.process import DesktopError
from bilge.tools.base import Tool, ToolError
from bilge.tools.desktop.common import choice, failure, int_argument, integer, obj, string_argument

VOLUME_STEP = 10


class VolumeAction(StrEnum):
    SET = "set"
    INCREASE = "increase"
    DECREASE = "decrease"
    MUTE = "mute"
    UNMUTE = "unmute"


class MusicAction(StrEnum):
    PLAY = "play"
    PAUSE = "pause"
    TOGGLE = "toggle"
    NEXT = "next"
    PREVIOUS = "previous"
    NOW_PLAYING = "nowPlaying"


_TEXTS = {
    AssistantLanguage.TURKISH: {
        "volume": "Bilgisayarın ses seviyesini ayarlar, artırır, azaltır, sessize alır ya da sesi açar.",
        "level": "Sadece 'set' için hedef seviye (0-100)",
        "no_level": "Hedef seviye belirtilmedi.",
        "level_now": "Ses seviyesi yüzde {level}.",
        "muted": "Ses kapatıldı.",
        "unmuted": "Ses açıldı, seviye yüzde {level}.",
        "music": "Açık müzik ya da video çaların (Spotify, Rhythmbox, VLC, tarayıcı) çalmasını başlatır, duraklatır, sonraki/önceki parçaya geçer ya da çalanı söyler.",
        "no_player": "Açık bir müzik çalar bulamadım.",
        "nothing_playing": "Şu an çalan bir şey yok.",
        "now_playing": "Çalan: {song}.",
        MusicAction.PLAY: "{player} çalıyor.",
        MusicAction.PAUSE: "{player} duraklatıldı.",
        MusicAction.TOGGLE: "{player} oynat/duraklat yapıldı.",
        MusicAction.NEXT: "Sonraki parçaya geçildi.",
        MusicAction.PREVIOUS: "Önceki parçaya dönüldü.",
    },
    AssistantLanguage.ENGLISH: {
        "volume": "Sets, raises or lowers the computer's volume, or mutes and unmutes it.",
        "level": "Only for 'set': the target level (0-100)",
        "no_level": "No target level was given.",
        "level_now": "The volume is at {level} percent.",
        "muted": "Sound is muted.",
        "unmuted": "Sound is back on, at {level} percent.",
        "music": "Plays, pauses, skips or goes back in the open music or video player (Spotify, Rhythmbox, VLC, a browser), or says what is playing.",
        "no_player": "I couldn't find an open music player.",
        "nothing_playing": "Nothing is playing right now.",
        "now_playing": "Playing: {song}.",
        MusicAction.PLAY: "{player} is playing.",
        MusicAction.PAUSE: "{player} is paused.",
        MusicAction.TOGGLE: "Toggled play and pause in {player}.",
        MusicAction.NEXT: "Skipped to the next track.",
        MusicAction.PREVIOUS: "Went back to the previous track.",
    },
}


def volume_tool(volume: Volume, language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]

    def run(arguments: dict[str, Any]) -> str:
        action = string_argument(arguments, "action")
        level = int_argument(arguments, "level")
        try:
            if action == VolumeAction.MUTE:
                volume.set_muted(True)
                return texts["muted"]
            if action == VolumeAction.UNMUTE:
                volume.set_muted(False)
                return texts["unmuted"].format(level=volume.state().level)
            if action == VolumeAction.SET:
                if level is None:
                    raise ToolError(texts["no_level"])
                target = level
            elif action in (VolumeAction.INCREASE, VolumeAction.DECREASE):
                step = VOLUME_STEP if action == VolumeAction.INCREASE else -VOLUME_STEP
                target = volume.state().level + step
            else:
                raise ToolError(texts["no_level"])
            target = max(0, min(100, target))
            volume.set_level(target)
            return texts["level_now"].format(level=target)
        except DesktopError as error:
            raise failure(error, language) from error

    parameters = obj(
        ["action"], action=choice(VolumeAction, "set/increase/decrease/mute/unmute"),
        level=integer(texts["level"], 0, 100),
    )  # fmt: skip
    return Tool("setVolume", texts["volume"], run=run, parameters=parameters)


def music_tool(media: Media, language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]

    def run(arguments: dict[str, Any]) -> str:
        try:
            action = MusicAction(string_argument(arguments, "action"))
        except ValueError:
            action = MusicAction.TOGGLE
        try:
            if action is MusicAction.NOW_PLAYING:
                playing = media.now_playing()
                if playing is None:
                    return texts["no_player"]
                if not playing.playing or not playing.title:
                    return texts["nothing_playing"]
                song = f"{playing.title} - {playing.artist}" if playing.artist else playing.title
                return texts["now_playing"].format(song=song)
            if media.now_playing() is None:
                return texts["no_player"]
            player = media.send(MediaCommand(action.value))
        except DesktopError as error:
            raise failure(error, language) from error
        return texts[action].format(player=player)

    # Track titles can be set by whoever made the video or page that is playing.
    return Tool("controlMusic", texts["music"], run=run, parameters=obj(["action"], action=choice(MusicAction, "")),
                untrusted_output=lambda arguments: arguments.get("action") == MusicAction.NOW_PLAYING)  # fmt: skip
