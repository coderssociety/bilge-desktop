"""Everyday commands recognized by rule, skipping both model calls (~1.2 s). The rules are narrow
on purpose: anything with extra content (a label, a second action, an unknown word) returns None
and goes to the model, so the fast path can only be faster, never wronger."""

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from bilge.core.text import folded
from bilge.core.tools import timer_phrase_parser, turkish_arithmetic_parser


@dataclass(frozen=True)
class SetVolume:
    level: int


class VolumeStep(StrEnum):
    UP = "up"
    DOWN = "down"
    MUTE = "mute"
    UNMUTE = "unmute"


VolumeChange = SetVolume | VolumeStep


class MediaAction(StrEnum):
    PLAY = "play"
    PAUSE = "pause"
    NEXT = "next"
    PREVIOUS = "previous"
    NOW_PLAYING = "nowPlaying"


class SystemAction(StrEnum):
    LOCK_SCREEN = "lockScreen"
    SLEEP = "sleep"
    DARK_MODE_ON = "darkModeOn"
    DARK_MODE_OFF = "darkModeOff"


class CalendarRange(StrEnum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    THIS_WEEK = "thisWeek"


class Folder(StrEnum):
    DESKTOP = "desktop"
    DOWNLOADS = "downloads"
    DOCUMENTS = "documents"


class TimerAction(StrEnum):
    LIST = "list"
    CANCEL_ALL = "cancelAll"


class WindowAction(StrEnum):
    MINIMIZE = "minimize"
    FULL_SCREEN = "fullScreen"
    LEFT_HALF = "leftHalf"
    RIGHT_HALF = "rightHalf"
    MAXIMIZE = "maximize"
    HIDE_OTHERS = "hideOthers"


class SystemInfoTopic(StrEnum):
    DISK = "disk"
    UPTIME = "uptime"
    OS_VERSION = "osVersion"
    NETWORK = "network"


class SettingsPane(StrEnum):
    WIFI = "wifi"
    BLUETOOTH = "bluetooth"
    NETWORK = "network"
    SOUND = "sound"
    DISPLAYS = "displays"
    BATTERY = "battery"
    NOTIFICATIONS = "notifications"
    FOCUS = "focus"
    PRIVACY = "privacy"
    KEYBOARD = "keyboard"
    GENERAL = "general"
    WALLPAPER = "wallpaper"
    SOFTWARE_UPDATE = "softwareUpdate"
    STORAGE = "storage"
    ACCESSIBILITY = "accessibility"
    TRACKPAD = "trackpad"
    MOUSE = "mouse"


@dataclass(frozen=True)
class DateTime:
    pass


@dataclass(frozen=True)
class Battery:
    pass


@dataclass(frozen=True)
class Reminders:
    pass


@dataclass(frozen=True)
class Clipboard:
    pass


@dataclass(frozen=True)
class OpenFolder:
    folder: Folder


@dataclass(frozen=True)
class Timers:
    action: TimerAction


@dataclass(frozen=True)
class Volume:
    change: VolumeChange


@dataclass(frozen=True)
class Media:
    action: MediaAction


@dataclass(frozen=True)
class System:
    action: SystemAction


@dataclass(frozen=True)
class Calendar:
    range: CalendarRange


@dataclass(frozen=True)
class Calculate:
    expression: str


@dataclass(frozen=True)
class Timer:
    seconds: int


@dataclass(frozen=True)
class Alarm:
    hour: int
    minute: int


@dataclass(frozen=True)
class OpenApp:
    name: str


@dataclass(frozen=True)
class QuitApp:
    name: str


@dataclass(frozen=True)
class Screenshot:
    pass


@dataclass(frozen=True)
class Wifi:
    on: bool


@dataclass(frozen=True)
class Window:
    action: WindowAction


@dataclass(frozen=True)
class Settings:
    pane: SettingsPane


@dataclass(frozen=True)
class SystemInfo:
    topic: SystemInfoTopic


QuickIntent = (
    DateTime
    | Battery
    | Reminders
    | Clipboard
    | OpenFolder
    | Timers
    | Volume
    | Media
    | System
    | Calendar
    | Calculate
    | Timer
    | Alarm
    | OpenApp
    | QuitApp
    | Screenshot
    | Wifi
    | Window
    | Settings
    | SystemInfo
)

_MAX_APP_NAME_WORDS = 3
_MAX_VOLUME = 100


def parse(text: str) -> QuickIntent | None:
    """`text` should already be digitized and time-resolved (turkish_number_parser, turkish_time_of_day)."""
    from bilge.core.conversation import mac_quick_intents

    original = [token for token in (_trim_punctuation(raw) for raw in text.split()) if token]
    words, kept = _simplified([folded(token) for token in original], original)
    if not words:
        return None
    word_rules: tuple[Callable[[list[str]], QuickIntent | None], ...] = (
        _date_time, _battery, _volume, _media, _system, _calendar, _reminders, _clipboard, _folder, _timers,
    )  # fmt: skip
    for rule in word_rules:
        intent = rule(words)
        if intent is not None:
            return intent
    intent = mac_quick_intents.parse(words)
    if intent is not None:
        return intent
    intent = _timer(words, text)
    if intent is not None:
        return intent
    expression = turkish_arithmetic_parser.expression(text)
    if expression is not None:
        return Calculate(expression)
    return _app(words, kept)


def _trim_punctuation(token: str) -> str:
    """Strips punctuation except the ASCII apostrophe, which app names like "Safari'yi" keep."""
    start, end = 0, len(token)
    while start < end and _is_trimmable(token[start]):
        start += 1
    while end > start and _is_trimmable(token[end - 1]):
        end -= 1
    return token[start:end]


def _is_trimmable(ch: str) -> bool:
    return ch != "'" and unicodedata.category(ch).startswith("P")


# Politeness

# Question-form verbs this parser knows, mapped to the imperative its rules expect
# ("kilitler misin" becomes "kilitle"). Unknown verbs stay as they are and fall through to the model.
_AORIST_TO_IMPERATIVE: dict[str, str] = {
    "kilitler": "kilitle", "gecer": "gec", "acar": "ac", "kapatir": "kapat", "okur": "oku", "baslatir": "baslat",
    "durdurur": "durdur", "duraklatir": "duraklat", "kisar": "kis", "artirir": "artir", "yukseltir": "yukselt",
    "azaltir": "azalt", "soyler": "soyle", "listeler": "listele", "kurar": "kur", "uyutur": "uyut", "alir": "al",
    "calar": "cal", "getirir": "getir", "yapar": "yap", "gosterir": "goster", "eder": "et", "siler": "sil",
}  # fmt: skip
_QUESTION_PARTICLES = frozenset({"misin", "musun", "misiniz", "musunuz"})
_TRAILING_POLITENESS = frozenset({"lutfen", "acaba", "hemen"})
_LEADING_POLITENESS = frozenset({"simdi", "hemen", "lutfen"})


def _simplified(words: list[str], original: list[str]) -> tuple[list[str], list[str]]:
    """Drops "şu an", "lütfen", "acaba" and turns "…ar mısın" into an imperative, on folded words
    and the matching original tokens alike (app names are taken from the originals)."""
    pairs = list(zip(words, original, strict=True))
    if len(pairs) > 2 and pairs[0][0] == "su" and pairs[1][0] == "an":
        pairs = pairs[2:]
    while len(pairs) > 1 and pairs[0][0] in _LEADING_POLITENESS:
        pairs = pairs[1:]
    while len(pairs) > 1 and pairs[-1][0] in _TRAILING_POLITENESS:
        pairs = pairs[:-1]
    if len(pairs) >= 2 and pairs[-1][0] in _QUESTION_PARTICLES:
        imperative = _AORIST_TO_IMPERATIVE.get(pairs[-2][0])
        if imperative is not None:
            pairs = [*pairs[:-2], (imperative, imperative)]
    return [word for word, _ in pairs], [token for _, token in pairs]


# Rules

_DATE_TIME_PHRASES = (
    ["saat", "kac"], ["saat", "kac", "oldu"], ["saat", "kac", "acaba"], ["saat", "kac", "oldu", "acaba"],
    ["bugun", "gunlerden", "ne"], ["tarih", "ne"], ["bugunun", "tarihi", "ne"], ["ayin", "kaci"],
    ["bugun", "ayin", "kaci"], ["bugun", "ne", "gunu"],
)  # fmt: skip


def _date_time(w: list[str]) -> QuickIntent | None:
    return DateTime() if w in _DATE_TIME_PHRASES else None


_BATTERY_WORDS = ("pil", "sarj", "batarya")
_BATTERY_ALLOWED = frozenset({"durumu", "durum", "kac", "ne", "kadar", "nedir", "durumda", "yuzde", "seviyesi", "oldu"})
_MAX_BATTERY_WORDS = 5


def _battery(w: list[str]) -> QuickIntent | None:
    if len(w) > _MAX_BATTERY_WORDS or not w[0].startswith(_BATTERY_WORDS):
        return None
    return Battery() if all(word in _BATTERY_ALLOWED for word in w[1:]) else None


_SET_VOLUME_VERBS = frozenset({"yap", "getir", "ayarla", "indir", "cek", "dusur", "cikar"})
_UP_VOLUME_VERBS = frozenset({"artir", "arttir", "yukselt"})
_DOWN_VOLUME_VERBS = frozenset({"kis", "azalt", "dusur", "alcalt"})
_MAX_VOLUME_WORDS = 4


def _volume(w: list[str]) -> QuickIntent | None:
    if w == ["sessize", "al"]:
        return Volume(VolumeStep.MUTE)
    if not w or w[0] != "sesi" or not 2 <= len(w) <= _MAX_VOLUME_WORDS:
        return None
    rest = w[1:]
    level_words = rest[:-1]
    if rest[-1] in _SET_VOLUME_VERBS:
        level = next((n for n in map(_leading_number, level_words) if n is not None), None)
        if level is not None and all(word == "yuzde" or _leading_number(word) is not None for word in level_words):
            return Volume(SetVolume(min(level, _MAX_VOLUME)))
    if rest == ["kapat"]:
        return Volume(VolumeStep.MUTE)
    if rest == ["ac"]:
        return Volume(VolumeStep.UNMUTE)
    if rest == ["biraz", "ac"]:
        return Volume(VolumeStep.UP)
    body = rest[1:] if rest[0] == "biraz" else rest
    if len(body) != 1:
        return None
    if body[0] in _UP_VOLUME_VERBS:
        return Volume(VolumeStep.UP)
    if body[0] in _DOWN_VOLUME_VERBS:
        return Volume(VolumeStep.DOWN)
    return None


_MEDIA_SUBJECTS = frozenset({"muzigi", "sarkiyi", "calmayi"})
_NEXT_PHRASES = (
    ["sonraki", "sarkiya", "gec"], ["sonraki", "sarki"], ["siradaki", "sarki"], ["sonraki", "parca"],
    ["sonraki", "sarkiyi", "cal"], ["siradaki", "sarkiya", "gec"],
)  # fmt: skip
_PREVIOUS_PHRASES = (
    ["onceki", "sarki"], ["bir", "onceki", "sarkiyi", "cal"], ["onceki", "sarkiyi", "cal"],
    ["onceki", "sarkiya", "don"], ["onceki", "parca"],
)  # fmt: skip
_NOW_PLAYING_PHRASES = (
    ["bu", "sarkinin", "adi", "ne"], ["calan", "sarki", "ne"], ["bu", "hangi", "sarki"],
    ["calan", "sarki", "hangisi"], ["ne", "caliyor"], ["su", "an", "ne", "caliyor"],
)  # fmt: skip


def _media(w: list[str]) -> QuickIntent | None:
    if len(w) == 2 and w[0] in _MEDIA_SUBJECTS:
        match w[1]:
            case "durdur" | "duraklat":
                return Media(MediaAction.PAUSE)
            case "baslat" | "cal" | "ac":
                return Media(MediaAction.PLAY) if w[0] == "muzigi" else None
            case "gec" | "degistir":
                return Media(MediaAction.NEXT) if w[0] == "sarkiyi" else None
            case _:
                return None
    if w in _NEXT_PHRASES:
        return Media(MediaAction.NEXT)
    if w in _PREVIOUS_PHRASES:
        return Media(MediaAction.PREVIOUS)
    return Media(MediaAction.NOW_PLAYING) if w in _NOW_PLAYING_PHRASES else None


_LOCK_SUBJECTS = frozenset({"ekrani", "maci", "bilgisayari"})
_SLEEP_PHRASES = (
    ["bilgisayari", "uyut"], ["maci", "uyut"], ["uyku", "moduna", "al"], ["bilgisayari", "uyku", "moduna", "al"],
    ["maci", "uyku", "moduna", "al"],
)  # fmt: skip
_DARK_ON_PHRASES = (
    ["karanlik", "modu", "ac"], ["karanlik", "moda", "gec"], ["koyu", "moda", "gec"], ["karanlik", "mod"],
    ["koyu", "modu", "ac"],
)  # fmt: skip
_DARK_OFF_PHRASES = (
    ["aydinlik", "moda", "gec"], ["karanlik", "modu", "kapat"], ["acik", "moda", "gec"], ["aydinlik", "modu", "ac"],
    ["aydinlik", "mod"],
)  # fmt: skip


def _system(w: list[str]) -> QuickIntent | None:
    if w[-1] == "kilitle" and len(w) <= 2 and (len(w) == 1 or w[0] in _LOCK_SUBJECTS):
        return System(SystemAction.LOCK_SCREEN)
    if w in _SLEEP_PHRASES:
        return System(SystemAction.SLEEP)
    if w in _DARK_ON_PHRASES:
        return System(SystemAction.DARK_MODE_ON)
    return System(SystemAction.DARK_MODE_OFF) if w in _DARK_OFF_PHRASES else None


_CALENDAR_TAILS = (["ne", "var"], ["neler", "var"])


def _calendar(w: list[str]) -> QuickIntent | None:
    def matches(prefix: list[str]) -> bool:
        if len(w) < len(prefix) + 2 or w[: len(prefix)] != prefix:
            return False
        middle = w[len(prefix) : -2]
        return len(middle) <= 1 and all(word.startswith("takvim") for word in middle) and w[-2:] in _CALENDAR_TAILS

    if matches(["bugun"]):
        return Calendar(CalendarRange.TODAY)
    if matches(["yarin"]):
        return Calendar(CalendarRange.TOMORROW)
    if matches(["bu", "hafta"]):
        return Calendar(CalendarRange.THIS_WEEK)
    return None


_REMINDER_SUBJECTS = frozenset({"animsaticilarimi", "animsaticilari", "yapilacaklarimi", "yapilacaklari"})
_REMINDER_VERBS = frozenset({"oku", "soyle", "listele"})


def _reminders(w: list[str]) -> QuickIntent | None:
    if len(w) == 2 and w[0] in _REMINDER_SUBJECTS and w[1] in _REMINDER_VERBS:
        return Reminders()
    if len(w) == 3 and w[0] == "yapilacaklar" and w[1] == "listemi" and w[2] in _REMINDER_VERBS:
        return Reminders()
    return None


_CLIPBOARD_PHRASES = (["panoyu", "oku"], ["panoda", "ne", "var"])


def _clipboard(w: list[str]) -> QuickIntent | None:
    if w in _CLIPBOARD_PHRASES:
        return Clipboard()
    if (
        len(w) == 3
        and w[0] in ("panodaki", "kopyaladigim")
        and w[1] in ("metni", "yaziyi", "seyi")
        and w[2] in ("oku", "soyle")
    ):
        return Clipboard()
    return None


_FOLDERS: dict[str, Folder] = {
    "masaustunu": Folder.DESKTOP, "masaustu": Folder.DESKTOP, "indirilenleri": Folder.DOWNLOADS,
    "indirilenler": Folder.DOWNLOADS, "belgeleri": Folder.DOCUMENTS, "belgeler": Folder.DOCUMENTS,
    "dokumanlari": Folder.DOCUMENTS, "dokumanlar": Folder.DOCUMENTS,
}  # fmt: skip


def _folder(w: list[str]) -> QuickIntent | None:
    if w[-1] != "ac" or len(w) not in (2, 3) or w[0] not in _FOLDERS:
        return None
    if len(w) == 3 and w[1] not in ("klasorunu", "klasoru"):
        return None
    return OpenFolder(_FOLDERS[w[0]])


_TIMER_SUBJECTS = frozenset({"alarmlari", "zamanlayicilari", "alarmlarimi", "zamanlayicilarimi"})
_CANCEL_VERBS = (["kapat"], ["sil"], ["iptal", "et"], ["iptal"])
_TIMER_LIST_PHRASES = (
    ["kurulu", "zamanlayicilar", "neler"], ["kurulu", "alarmlar", "neler"], ["hangi", "alarmlar", "kurulu"],
    ["hangi", "zamanlayicilar", "kurulu"],
)  # fmt: skip


def _timers(w: list[str]) -> QuickIntent | None:
    body = w[1:] if w[0] in ("butun", "tum") else w
    if body and body[0] in _TIMER_SUBJECTS:
        verb = body[1:]
        if verb in _CANCEL_VERBS:
            return Timers(TimerAction.CANCEL_ALL)
        if verb in (["listele"], ["oku"]):
            return Timers(TimerAction.LIST)
    return Timers(TimerAction.LIST) if w in _TIMER_LIST_PHRASES else None


_TIMER_TRIGGERS = frozenset({"zamanlayici", "zamanlayicisi", "alarm", "uyar", "uyandir"})
_TIMER_ALLOWED = _TIMER_TRIGGERS | {
    "dakika", "dakikalik", "saniye", "saniyelik", "saat", "saatlik", "sonra", "kur", "baslat", "ayarla", "beni",
    "bucuk", "yarin", "bir", "yarim", "ceyrek",
}  # fmt: skip


def _timer(w: list[str], text: str) -> QuickIntent | None:
    """Only bare timers and wake-up alarms; "çayı hatırlat" carries a label, so the model handles it."""
    if not any(word in _TIMER_TRIGGERS for word in w):
        return None
    if not all(word in _TIMER_ALLOWED or _leading_number(word) is not None for word in w):
        return None
    parsed = timer_phrase_parser.parse(text)
    if parsed is None:
        return None
    if parsed.hour is not None:
        return Alarm(hour=parsed.hour, minute=parsed.minute or 0)
    return Timer(seconds=parsed.duration_seconds) if parsed.duration_seconds is not None else None


_OPEN_ENDINGS = (["ac"], ["baslat"], ["acar", "misin"], ["acsana"], ["acabilir", "misin"])
_QUIT_ENDINGS = (["kapat"], ["kapatir", "misin"], ["kapatsana"], ["kapatabilir", "misin"])
_APP_SUFFIX_WORDS = frozenset({"uygulamasini", "uygulamasi", "programini"})


def _app(w: list[str], original: list[str]) -> QuickIntent | None:
    for endings, make in ((_OPEN_ENDINGS, OpenApp), (_QUIT_ENDINGS, QuitApp)):
        for ending in endings:
            if len(w) <= len(ending) or w[-len(ending) :] != ending:
                continue
            name_words = original[: -len(ending)]
            if name_words and folded(name_words[-1]) in _APP_SUFFIX_WORDS:
                name_words = name_words[:-1]
            if not 1 <= len(name_words) <= _MAX_APP_NAME_WORDS:
                return None
            if any(_is_not_an_app_word(folded(word)) for word in name_words):
                return None
            return make(" ".join(name_words))
    return None


_NON_APP_PREFIXES = (
    "ses", "muzi", "sarki", "bilgisayar", "mac", "ekran", "bluetooth", "wifi", "wi", "internet", "odak",
    "rahatsiz", "mod", "karanlik", "aydinlik", "isik", "masaustu", "indirilen", "belge", "klasor", "dosya",
    "pencere", "zamanlayici", "alarm", "parlaklik", "bildirim", "kamera", "mikrofon", "ondan", "sonra", "ve", "ayar",
)  # fmt: skip


def _is_not_an_app_word(word: str) -> bool:
    return word.startswith(_NON_APP_PREFIXES) or "mod" in word


def _leading_number(word: str) -> int | None:
    digits = ""
    for ch in word:
        if not ch.isnumeric():
            break
        digits += ch
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        # Numeric characters without a decimal value ("½"); Swift's Int() rejects them too.
        return None
