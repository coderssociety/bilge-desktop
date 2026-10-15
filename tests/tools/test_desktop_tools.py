import threading
from datetime import datetime
from types import SimpleNamespace

import pytest

from bilge.core.language import AssistantLanguage
from bilge.desktop.base import AppEntry, FrontWindow, MediaCommand, NowPlaying, VolumeState
from bilge.desktop.process import MissingProgram
from bilge.tools.base import ToolError
from bilge.tools.desktop import apps, clipboard, sound, system, timers, typing, web

TR, EN = AssistantLanguage.TURKISH, AssistantLanguage.ENGLISH


def by_name(tools):
    return {tool.name: tool for tool in tools}


class FakeApps:
    def __init__(self):
        self.entries = [AppEntry("calc", "Hesap Makinesi", ("Hesap Makinesi", "Calculator")),
                        AppEntry("ff", "Firefox", ("Firefox", "Web Tarayıcısı"))]  # fmt: skip
        self.launched, self.quit_ids, self.open = [], [], {"ff"}

    def installed(self):
        return self.entries

    def launch(self, app):
        self.launched.append(app.id)

    def running(self):
        return [e for e in self.entries if e.id in self.open]

    def quit(self, app):
        self.quit_ids.append(app.id)
        return app.id in self.open


def test_open_app_by_its_spoken_turkish_name():
    fake = FakeApps()
    tools = by_name(apps.app_tools(apps.AppCatalog(fake), TR))
    assert tools["openApp"].run({"appName": "hesap makinesini"}) == "Hesap Makinesi açıldı."
    assert fake.launched == ["calc"]
    with pytest.raises(ToolError, match="Fotoşop"):
        tools["openApp"].run({"appName": "Fotoşop"})


def test_quitting_asks_first_and_says_when_it_was_not_open():
    fake = FakeApps()
    quit_app = by_name(apps.app_tools(apps.AppCatalog(fake), TR))["quitApp"]
    assert (
        quit_app.question({"appName": "firefox"}) == "Firefox kapatılsın mı? Kaydedilmemiş değişiklikler kaybolabilir."
    )
    assert quit_app.run({"appName": "firefox"}) == "Firefox kapatılıyor."
    assert quit_app.run({"appName": "hesap makinesi"}) == "Hesap Makinesi zaten kapalı."


def test_running_apps_are_listed():
    tools = by_name(apps.app_tools(apps.AppCatalog(FakeApps()), EN))
    assert tools["listRunningApps"].run({}) == "Open apps: Firefox."


class FakeVolume:
    def __init__(self, level=50):
        self.level, self.muted = level, False

    def state(self):
        return VolumeState(self.level, self.muted)

    def set_level(self, level):
        self.level = level

    def set_muted(self, muted):
        self.muted = muted


def test_volume_steps_stay_within_bounds():
    fake = FakeVolume(95)
    tool = sound.volume_tool(fake, TR)
    assert tool.run({"action": "increase"}) == "Ses seviyesi yüzde 100."
    assert tool.run({"action": "set", "level": "30"}) == "Ses seviyesi yüzde 30."
    assert tool.run({"action": "mute"}) == "Ses kapatıldı."
    assert tool.run({"action": "unmute"}) == "Ses açıldı, seviye yüzde 30."
    with pytest.raises(ToolError, match="Hedef seviye"):
        tool.run({"action": "set"})


def test_missing_sound_program_is_named_to_the_user():
    class Broken(FakeVolume):
        def state(self):
            raise MissingProgram("wpctl", "pactl", "amixer")

    with pytest.raises(ToolError, match="wpctl, pactl, amixer"):
        sound.volume_tool(Broken(), TR).run({"action": "increase"})


class FakeMedia:
    def __init__(self, playing):
        self.playing, self.sent = playing, []

    def now_playing(self):
        return self.playing

    def send(self, command):
        self.sent.append(command)
        return self.playing.player


def test_music_control_and_now_playing():
    media = FakeMedia(NowPlaying("Spotify", True, "Gesi Bağları", "Zeki Müren"))
    tool = sound.music_tool(media, TR)
    assert tool.run({"action": "nowPlaying"}) == "Çalan: Gesi Bağları - Zeki Müren."
    assert tool.run({"action": "pause"}) == "Spotify duraklatıldı."
    assert media.sent == [MediaCommand.PAUSE]
    assert sound.music_tool(FakeMedia(None), TR).run({"action": "play"}) == "Açık bir müzik çalar bulamadım."


def test_battery_states():
    def tool(percent, plugged):
        return system.battery_tool(TR, read=lambda: SimpleNamespace(percent=percent, power_plugged=plugged))

    assert tool(54.4, False).run({}) == "Pil yüzde 54, pilden çalışıyor."
    assert tool(80, True).run({}) == "Pil yüzde 80, şarj oluyor."
    assert system.battery_tool(TR, read=lambda: None).run({}) == "Bu bilgisayarda pil yok, prize bağlı çalışıyor."


def test_turning_wifi_off_asks_but_on_does_not():
    class Network:
        def wifi_enabled(self):
            return True

        def set_wifi(self, enabled):
            self.enabled = enabled

    tool = system.wifi_tool(Network(), TR)
    assert tool.question({"power": "on"}) is None
    assert "internet bağlantın kesilir" in tool.question({"power": "off"})
    assert tool.run({"power": "off"}) == "Wi-Fi kapatıldı."


def test_screenshot_goes_to_a_folder_in_pictures(tmp_path):
    class Shots:
        def capture(self, area, destination):
            destination.write_bytes(b"png")
            self.destination = destination
            return True

    folders = SimpleNamespace(pictures=lambda: tmp_path)
    shots = Shots()
    tool = system.screenshot_tool(shots, folders, TR, clock=lambda: datetime(2026, 10, 15, 9, 5, 7))
    assert tool.run({}) == "Ekran görüntüsünü Ekran Görüntüleri klasörüne kaydettim."
    assert shots.destination == tmp_path / "Ekran Görüntüleri" / "Ekran görüntüsü 2026-10-15 09.05.07.png"


def test_uptime_is_said_in_words():
    texts = system._TEXTS[TR]
    assert system._elapsed(3 * 86400 + 5 * 3600 + 120, texts) == "3 gün 5 saat"
    assert system._elapsed(2 * 3600 + 15 * 60, texts) == "2 saat 15 dakika"
    assert system._elapsed(30, texts) == "0 dakika"


class FakeClipboard:
    def __init__(self, content="", selected=""):
        self.content, self.selected = content, selected

    def read(self):
        return self.content

    def write(self, text):
        self.content = text

    def selection(self):
        return self.selected


def test_clipboard_reads_are_untrusted_and_copy_falls_back_to_the_last_reply():
    fake = FakeClipboard("x" * 2000)
    tools = by_name(clipboard.clipboard_tools(fake, TR, last_reply=lambda: "Saat 14:05."))
    assert tools["readClipboard"].untrusted_output and tools["readSelection"].untrusted_output
    assert tools["readClipboard"].run({}).endswith("…")
    assert tools["copyToClipboard"].run({}) == "Panoya kopyaladım."
    assert fake.content == "Saat 14:05."
    with pytest.raises(ToolError, match="Seçili"):
        tools["readSelection"].run({})


GEDIT = FrontWindow("gedit")


class FakeKeyboard:
    def __init__(self, front=GEDIT):
        self.front, self.typed, self.events = front, [], []

    def front_window(self):
        return self.front

    def type(self, text):
        self.typed.append(text)
        self.events.append(("type", text))

    def new_line(self):
        self.events.append(("newline",))

    def backspace(self, count):
        self.events.append(("backspace", count))


def test_typing_refuses_terminals_and_asks_when_the_front_app_is_unknown():
    tool = typing.type_text_tool(FakeKeyboard(FrontWindow("gnome-terminal-server")), TR)
    with pytest.raises(ToolError, match="terminallere"):
        tool.run({"text": "rm -rf ~"})
    unknown = typing.type_text_tool(FakeKeyboard(front=None), TR)
    assert unknown.question({"text": "x"}) == "Öndeki pencereyi göremiyorum; imlecin olduğu yere yazayım mı?"
    keyboard = FakeKeyboard()
    typing.type_text_tool(keyboard, TR).run({"text": "satır\nsonu\tyok"})
    assert "\n" not in keyboard.typed[0] and "\t" not in keyboard.typed[0]


def test_jetbrains_password_managers_and_terminals_by_class_are_refused():
    assert typing.refuses(FrontWindow("jetbrains-pycharm"))
    assert typing.refuses(FrontWindow("KeePassXC"))
    # A terminal written in Python runs as python3; a Flatpak terminal is known by its app id.
    assert typing.refuses(FrontWindow("python3.12", app_class="terminator"))
    assert typing.refuses(FrontWindow("", app_class="org.gnome.Console"))
    assert not typing.refuses(FrontWindow("libreoffice", app_class="libreoffice-writer"))


def test_dictation_with_an_unchecked_window_ends_sooner():
    session = typing.DictationSession(FakeKeyboard(front=None), TR)
    session.begin(None)
    checked = typing.DictationSession(FakeKeyboard(), TR)
    checked.begin(typing.front_app(checked.keyboard))
    assert session.window() < checked.window()


def test_dictation_types_controls_and_stops_when_the_front_app_changes():
    keyboard = FakeKeyboard()
    session = typing.DictationSession(keyboard, TR)
    start = typing.start_dictation_tool(session, TR)
    assert start.question({}) is None
    assert start.run({}) == "Dikte açık, gedit uygulamasına yazıyorum. Bitirmek için 'dikteyi bitir' de."
    assert session.handle("merhaba nasılsın") == ""
    session.handle("yeni satır")
    session.handle("bugün hava güzel")
    assert session.handle("son cümleyi sil") == ""
    assert keyboard.events[0][0] == "type" and keyboard.events[1] == ("newline",)
    assert keyboard.events[-1] == ("backspace", len(keyboard.typed[-1]))
    keyboard.front = FrontWindow("firefox")
    assert session.handle("devam") == "Öndeki uygulama değişti, dikteyi bitirdim."
    assert not session.active


def test_dictation_finishes_on_request():
    keyboard = FakeKeyboard()
    session = typing.DictationSession(keyboard, EN)
    session.begin(typing.front_app(keyboard))
    assert typing.dictation_owns(session)("stop dictation")
    assert session.handle("stop dictation") == "Dictation is over."
    assert not session.active


def test_timers_fire_once_and_can_be_listed_and_cancelled():
    fired = []
    done = threading.Event()

    def announce(message):
        fired.append(message)
        done.set()

    clock = {"now": datetime(2026, 10, 15, 14, 0)}
    service = timers.TimerService(announce, TR, clock=lambda: clock["now"])
    tools = by_name(timers.timer_tools(service, TR, clock=lambda: clock["now"]))
    assert tools["setTimer"].run({"hour": 18, "minute": 30, "label": "çay"}) == "Tamam, saat 18:30 için kurdum."
    assert tools["setTimer"].run({"hour": 9}) == "Tamam, yarın saat 09:00 için kurdum."
    assert tools["manageTimers"].run({"action": "list"}) == "Zamanlayıcılar: 18:30 çay; 09:00"
    assert tools["manageTimers"].run({"action": "cancelAll"}) == "2 zamanlayıcı iptal edildi."
    assert not done.wait(0.3)
    service.schedule(datetime(2026, 10, 15, 14, 1), "su iç")
    # The clock jumping forward, as after the computer wakes up, makes a waiting timer go off.
    clock["now"] = datetime(2026, 10, 15, 14, 30)
    with service._changed:
        service._changed.notify()
    assert done.wait(2)
    assert fired == ["Hatırlatma: su iç."]
    assert service.timers == []


def test_timer_refine_takes_the_time_from_the_words():
    tool = by_name(timers.timer_tools(timers.TimerService(lambda _: None, TR), TR))["setTimer"]
    assert tool.refine({"hour": 19}, "20:00 için alarm kur") == {"hour": 20, "minute": 0, "minutes": None,
                                                                 "seconds": None}  # fmt: skip
    assert tool.refine({}, "10 dakika sonra haber ver")["minutes"] == 10


def test_only_web_addresses_are_opened():
    assert web.web_url("github.com") == "https://github.com"
    assert web.web_url("http://example.org/a b") == "http://example.org/ab"
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "localhost", "smb://server/share"):
        assert web.web_url(bad) is None


def test_search_opens_the_chosen_service():
    opened = []
    tools = by_name(web.web_tools(SimpleNamespace(open=opened.append), TR))
    assert tools["searchWeb"].run({"query": "kuru fasulye tarifi", "service": "youtube"}) == (
        "Tarayıcıda 'kuru fasulye tarifi' araması açıldı."
    )
    assert opened == ["https://www.youtube.com/results?search_query=kuru+fasulye+tarifi"]
    assert tools["openWebsite"].run({"address": "sahibinden.com"}) == "sahibinden.com açıldı."
