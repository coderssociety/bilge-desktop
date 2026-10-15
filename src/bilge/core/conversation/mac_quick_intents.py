"""Fast-path rules for Mac controls added with the larger tool set. Same contract as the rest of
quick_intent_parser: exact, narrow phrasings only; everything else goes to the model."""

from bilge.core.conversation.quick_intent_parser import (
    QuickIntent,
    Screenshot,
    Settings,
    SettingsPane,
    SystemInfo,
    SystemInfoTopic,
    Wifi,
    Window,
    WindowAction,
)


def parse(w: list[str]) -> QuickIntent | None:
    for rule in (_screenshot, _wifi, _window, _settings, _system_info):
        intent = rule(w)
        if intent is not None:
            return intent
    return None


_SCREENSHOT_PHRASES = (
    ["ekran", "goruntusu", "al"], ["ekran", "resmi", "al"], ["ekranin", "goruntusunu", "al"],
    ["ekran", "goruntusu", "cek"], ["ekranin", "resmini", "al"], ["ekran", "goruntusu"],
)  # fmt: skip


def _screenshot(w: list[str]) -> QuickIntent | None:
    return Screenshot() if w in _SCREENSHOT_PHRASES else None


_WIFI_SUBJECTS = ("wifi", "wifii", "wifiyi", "kablosuzu", "kablosuzagi")


def _wifi(w: list[str]) -> QuickIntent | None:
    """ "Wi-Fi'ı" folds to "wi fii", so the words are compared without spaces."""
    compact = "".join(w).replace(" ", "")
    for subject in _WIFI_SUBJECTS:
        if compact == subject + "ac":
            return Wifi(on=True)
        if compact == subject + "kapat":
            return Wifi(on=False)
    return None


_WINDOW_MINIMIZE = (["kucult"], ["simge", "durumuna", "kucult"], ["dock", "a", "indir"])
_WINDOW_FULL_SCREEN = (["tam", "ekran", "yap"], ["tam", "ekrana", "al"], ["tam", "ekran"])
_WINDOW_LEFT = (["sola", "al"], ["sola", "yasla"], ["ekranin", "soluna", "al"], ["sol", "yariya", "al"])
_WINDOW_RIGHT = (["saga", "al"], ["saga", "yasla"], ["ekranin", "sagina", "al"], ["sag", "yariya", "al"])
_WINDOW_MAXIMIZE = (["buyut"], ["ekrani", "kaplasin"])
_WINDOW_HIDE_OTHERS = (["digerlerini", "gizle"], ["diger", "uygulamalari", "gizle"], ["digerlerini", "sakla"])


def _window(w: list[str]) -> QuickIntent | None:
    names_window = bool(w) and w[0] == "pencereyi"
    body = w[1:] if names_window else w
    # These need "pencereyi": a bare "küçült" or "sola al" is too vague to act on.
    for phrases, action in (
        (_WINDOW_MINIMIZE, WindowAction.MINIMIZE),
        (_WINDOW_LEFT, WindowAction.LEFT_HALF),
        (_WINDOW_RIGHT, WindowAction.RIGHT_HALF),
        (_WINDOW_MAXIMIZE, WindowAction.MAXIMIZE),
    ):
        if body in phrases:
            return Window(action) if names_window else None
    if body in _WINDOW_FULL_SCREEN:
        return Window(WindowAction.FULL_SCREEN)
    if body in _WINDOW_HIDE_OTHERS:
        return Window(WindowAction.HIDE_OTHERS)
    return None


_PANE_WORDS: tuple[tuple[list[str], SettingsPane], ...] = (
    (["wifi"], SettingsPane.WIFI), (["wi", "fi"], SettingsPane.WIFI), (["bluetooth"], SettingsPane.BLUETOOTH),
    (["ag"], SettingsPane.NETWORK), (["ses"], SettingsPane.SOUND), (["ekran"], SettingsPane.DISPLAYS),
    (["pil"], SettingsPane.BATTERY), (["bildirim"], SettingsPane.NOTIFICATIONS), (["odak"], SettingsPane.FOCUS),
    (["gizlilik"], SettingsPane.PRIVACY), (["guvenlik"], SettingsPane.PRIVACY), (["klavye"], SettingsPane.KEYBOARD),
    (["genel"], SettingsPane.GENERAL), (["duvar", "kagidi"], SettingsPane.WALLPAPER),
    (["yazilim", "guncelleme"], SettingsPane.SOFTWARE_UPDATE), (["depolama"], SettingsPane.STORAGE),
    (["erisilebilirlik"], SettingsPane.ACCESSIBILITY), (["izleme", "dortgeni"], SettingsPane.TRACKPAD),
    (["fare"], SettingsPane.MOUSE),
)  # fmt: skip
_SETTINGS_ENDINGS = (["ayarlarini", "ac"], ["ayarlarina", "git"], ["ayarlarini", "goster"])


def _settings(w: list[str]) -> QuickIntent | None:
    """ "<bölüm> ayarlarını aç" / "<bölüm> ayarlarına git"."""
    ending = next((e for e in _SETTINGS_ENDINGS if len(w) > len(e) and w[-len(e) :] == e), None)
    if ending is None:
        return None
    subject = [part for word in w[: -len(ending)] for part in word.split(" ")]
    return next((Settings(pane) for words, pane in _PANE_WORDS if words == subject), None)


_DISK_PHRASES = (
    ["diskte", "ne", "kadar", "yer", "var"], ["diskte", "ne", "kadar", "yer", "kaldi"],
    ["ne", "kadar", "bos", "yer", "var"], ["bos", "alan", "ne", "kadar"], ["disk", "doluluk", "orani"],
    ["ne", "kadar", "yer", "kaldi"],
)  # fmt: skip
_UPTIME_PHRASES = (
    ["bilgisayar", "ne", "zamandir", "acik"], ["mac", "ne", "zamandir", "acik"], ["ne", "zamandir", "aciksin"],
    ["bilgisayar", "kac", "gundur", "acik"],
)  # fmt: skip
_NETWORK_PHRASES = (["ip", "adresim", "ne"], ["ip", "adresim", "kac"], ["yerel", "ip", "adresim", "ne"])
_OS_PHRASES = (
    ["macos", "surumu", "ne"], ["hangi", "macos", "surumu", "yuklu"], ["isletim", "sistemi", "surumu", "ne"],
)  # fmt: skip


def _system_info(w: list[str]) -> QuickIntent | None:
    if w in _DISK_PHRASES:
        return SystemInfo(SystemInfoTopic.DISK)
    if w in _UPTIME_PHRASES:
        return SystemInfo(SystemInfoTopic.UPTIME)
    if w in _NETWORK_PHRASES:
        return SystemInfo(SystemInfoTopic.NETWORK)
    return SystemInfo(SystemInfoTopic.OS_VERSION) if w in _OS_PHRASES else None
