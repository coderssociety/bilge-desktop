"""The computer itself: locking, sleep, dark mode, battery, disk and memory, Wi-Fi, settings pages, screenshots."""

import platform
import socket
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import psutil

from bilge.core.conversation.quick_intent_parser import SettingsPane
from bilge.core.language import AssistantLanguage
from bilge.desktop.base import Folders, Network, ScreenshotArea, Screenshots, Session, SettingsPanes
from bilge.desktop.process import DesktopError
from bilge.tools.base import Risk, Tool
from bilge.tools.desktop.common import choice, failure, obj, string_argument

EN, TR = AssistantLanguage.ENGLISH, AssistantLanguage.TURKISH


class SystemAction(StrEnum):
    LOCK_SCREEN = "lockScreen"
    SLEEP = "sleep"
    DARK_MODE_ON = "darkModeOn"
    DARK_MODE_OFF = "darkModeOff"
    TOGGLE_DARK_MODE = "toggleDarkMode"


class InfoTopic(StrEnum):
    DISK = "disk"
    MEMORY = "memory"
    UPTIME = "uptime"
    OS_VERSION = "osVersion"
    NETWORK = "network"


_TEXTS = {
    TR: {
        "system": "Yalnızca şunları yapar: ekranı kilitlemek, bilgisayarı uyutmak, karanlık/aydınlık görünüme geçmek.",
        "locked": "Ekran kilitlendi.",
        "sleeping": "Bilgisayar uyku moduna alınıyor.",
        "sleep_question": "Bilgisayarı uyutayım mı?",
        "dark_on": "Karanlık mod açık.",
        "dark_off": "Karanlık mod kapalı.",
        "battery": "Pil doluluk yüzdesini ve şarj durumunu verir.",
        "no_battery": "Bu bilgisayarda pil yok, prize bağlı çalışıyor.",
        "battery_state": "Pil yüzde {percent}, {state}.",
        "charging": "şarj oluyor",
        "plugged": "prize bağlı",
        "discharging": "pilden çalışıyor",
        "info": "Bilgisayarın durumunu söyler: boş disk alanı, bellek kullanımı, ne zamandır açık olduğu, işletim sistemi sürümü, Wi-Fi ve IP adresi.",
        "disk": "Diskte {free} GB boş yer var, toplam {total} GB.",
        "memory": "{total} GB belleğin yaklaşık {used} GB'ı kullanımda.",
        "uptime": "Bilgisayar {elapsed} önce açıldı.",
        "days": "{n} gün", "hours": "{n} saat", "minutes": "{n} dakika",
        "os": "Bu bilgisayarda {os} çalışıyor.",
        "wifi_on": "Wi-Fi açık", "wifi_off": "Wi-Fi kapalı", "wifi_unknown": "Wi-Fi durumu okunamadı",
        "no_network": "{wifi}; ağ bağlantısı görünmüyor.",
        "network": "{wifi}. Yerel IP adresin {address}.",
        "wifi": "Wi-Fi'ı açar ya da kapatır.",
        "wifi_question": "Wi-Fi'ı kapatırsam internet bağlantın kesilir. Kapatayım mı?",
        "wifi_done_on": "Wi-Fi açıldı.", "wifi_done_off": "Wi-Fi kapatıldı.",
        "settings": "Sistem ayarlarının bir bölümünü açar: Wi-Fi, Bluetooth, ses, ekran, pil, bildirimler, gizlilik, klavye, duvar kağıdı, yazılım güncelleme gibi.",
        "settings_opened": "Ayarları açtım.",
        "settings_main": "Bu masaüstünde o bölüm yok; ayarların ana penceresini açtım.",
        "screenshot": "Ekran görüntüsü alır: tüm ekran, öndeki pencere ya da fareyle seçilen alan; Resimler klasörüne kaydeder ya da panoya kopyalar.",
        "area": "Belirtilmediyse wholeScreen",
        "to_clipboard": "Panoya kopyalanması istendiyse true",
        "shot_saved": "Ekran görüntüsünü {folder} klasörüne kaydettim.",
        "shot_copied": "Ekran görüntüsü panoya kopyalandı.",
        "shot_cancelled": "Ekran görüntüsü alınmadı.",
        "shot_name": "Ekran görüntüsü {stamp}.png",
        "shot_folder": "Ekran Görüntüleri",
    },
    EN: {
        "system": "Only does these: locks the screen, puts the computer to sleep, switches dark or light appearance.",
        "locked": "The screen is locked.",
        "sleeping": "Putting the computer to sleep.",
        "sleep_question": "Shall I put the computer to sleep?",
        "dark_on": "Dark mode is on.",
        "dark_off": "Dark mode is off.",
        "battery": "Gives the battery level and whether it's charging.",
        "no_battery": "This computer has no battery; it runs on mains power.",
        "battery_state": "The battery is at {percent} percent, {state}.",
        "charging": "charging",
        "plugged": "plugged in",
        "discharging": "running on battery",
        "info": "Tells the computer's status: free disk space, memory use, how long it's been on, the operating system version, Wi-Fi and IP address.",
        "disk": "There are {free} GB free on the disk, out of {total} GB.",
        "memory": "About {used} GB of {total} GB memory is in use.",
        "uptime": "The computer was started {elapsed} ago.",
        "days": "{n} days", "hours": "{n} hours", "minutes": "{n} minutes",
        "os": "This computer runs {os}.",
        "wifi_on": "Wi-Fi is on", "wifi_off": "Wi-Fi is off", "wifi_unknown": "I couldn't read the Wi-Fi state",
        "no_network": "{wifi}; there's no network connection.",
        "network": "{wifi}. Your local IP address is {address}.",
        "wifi": "Turns Wi-Fi on or off.",
        "wifi_question": "Turning Wi-Fi off cuts your internet connection. Shall I turn it off?",
        "wifi_done_on": "Wi-Fi is on.", "wifi_done_off": "Wi-Fi is off.",
        "settings": "Opens a page of the system settings: Wi-Fi, Bluetooth, sound, displays, battery, notifications, privacy, keyboard, wallpaper, software updates and so on.",
        "settings_opened": "I opened the settings.",
        "settings_main": "This desktop has no such page; I opened the main settings window.",
        "screenshot": "Takes a screenshot of the whole screen, the window in front, or an area chosen with the mouse; saves it in Pictures or copies it.",
        "area": "wholeScreen unless said otherwise",
        "to_clipboard": "true if it should be copied",
        "shot_saved": "I saved the screenshot in {folder}.",
        "shot_copied": "The screenshot is on the clipboard.",
        "shot_cancelled": "No screenshot was taken.",
        "shot_name": "Screenshot {stamp}.png",
        "shot_folder": "Screenshots",
    },
}  # fmt: skip


def system_action_tool(session: Session, language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]

    def run(arguments: dict[str, Any]) -> str:
        action = string_argument(arguments, "action")
        try:
            if action == SystemAction.LOCK_SCREEN:
                session.lock()
                return texts["locked"]
            if action == SystemAction.SLEEP:
                session.suspend()
                return texts["sleeping"]
            if action == SystemAction.TOGGLE_DARK_MODE:
                dark = not bool(session.dark_mode())
            else:
                dark = action == SystemAction.DARK_MODE_ON
            session.set_dark_mode(dark)
        except DesktopError as error:
            raise failure(error, language) from error
        return texts["dark_on" if dark else "dark_off"]

    def question(arguments: dict[str, Any]) -> str | None:
        # A misheard word must not put the computer to sleep in the middle of something.
        return texts["sleep_question"] if string_argument(arguments, "action") == SystemAction.SLEEP else None

    return Tool("systemAction", texts["system"], run=run, parameters=obj(["action"], action=choice(SystemAction, "")),
                risk=Risk.CONFIRM, confirmation=question)  # fmt: skip


def battery_tool(language: AssistantLanguage, read: Callable[[], Any] = psutil.sensors_battery) -> Tool:
    texts = _TEXTS[language]

    def run(_: dict[str, Any]) -> str:
        battery = read()
        if battery is None:
            return texts["no_battery"]
        percent = round(battery.percent)
        plugged_state = "plugged" if percent >= 100 else "charging"
        state = texts[plugged_state if battery.power_plugged else "discharging"]
        return texts["battery_state"].format(percent=percent, state=state)

    return Tool("batteryStatus", texts["battery"], run=run)


def system_info_tool(network: Network, folders: Folders, language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]

    def run(arguments: dict[str, Any]) -> str:
        topic = string_argument(arguments, "topic")
        if topic == InfoTopic.DISK:
            usage = psutil.disk_usage(str(folders.home()))
            return texts["disk"].format(free=_gigabytes(usage.free), total=_gigabytes(usage.total))
        if topic == InfoTopic.MEMORY:
            memory = psutil.virtual_memory()
            return texts["memory"].format(
                total=_gibibytes(memory.total), used=_gibibytes(memory.total - memory.available)
            )
        if topic == InfoTopic.UPTIME:
            return texts["uptime"].format(elapsed=_elapsed(time.time() - psutil.boot_time(), texts))
        if topic == InfoTopic.OS_VERSION:
            return texts["os"].format(os=os_name())
        return _network(network, texts)

    return Tool("systemInfo", texts["info"], run=run, parameters=obj(["topic"], topic=choice(InfoTopic, "")))


def os_name() -> str:
    if platform.system() == "Linux":
        try:
            pretty = platform.freedesktop_os_release().get("PRETTY_NAME")
        except OSError:
            pretty = None
        return pretty or f"Linux {platform.release()}"
    return f"{platform.system()} {platform.release()}"


def _network(network: Network, texts: dict[str, str]) -> str:
    try:
        enabled = network.wifi_enabled()
    except DesktopError:
        enabled = None
    wifi = texts["wifi_unknown"] if enabled is None else texts["wifi_on" if enabled else "wifi_off"]
    address = local_ipv4()
    return texts["network"].format(wifi=wifi, address=address) if address else texts["no_network"].format(wifi=wifi)


def local_ipv4() -> str | None:
    stats = psutil.net_if_stats()
    for name, addresses in psutil.net_if_addrs().items():
        if not stats.get(name) or not stats[name].isup:
            continue
        for address in addresses:
            if address.family == socket.AF_INET and not address.address.startswith("127."):
                return address.address
    return None


def _elapsed(seconds: float, texts: dict[str, str]) -> str:
    minutes = int(seconds // 60)
    days, hours, rest = minutes // 1440, minutes % 1440 // 60, minutes % 60
    parts = [
        texts["days"].format(n=days) if days else None,
        texts["hours"].format(n=hours) if hours else None,
        texts["minutes"].format(n=rest) if not days and (rest or not hours) else None,
    ]
    return " ".join(part for part in parts if part)


def _gibibytes(count: int) -> int:
    return round(count / (1 << 30))


def _gigabytes(count: int) -> int:
    return round(count / 1_000_000_000)


def wifi_tool(network: Network, language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]

    def turning_on(arguments: dict[str, Any]) -> bool:
        return string_argument(arguments, "power") != "off"

    def run(arguments: dict[str, Any]) -> str:
        on = turning_on(arguments)
        try:
            network.set_wifi(on)
        except DesktopError as error:
            raise failure(error, language) from error
        return texts["wifi_done_on" if on else "wifi_done_off"]

    # Turning Wi-Fi off cuts the connection, so only that direction asks first.
    return Tool("setWiFi", texts["wifi"], run=run, parameters=obj(["power"], power=choice(["on", "off"], "")),
                risk=Risk.CONFIRM,
                confirmation=lambda arguments: None if turning_on(arguments) else texts["wifi_question"])  # fmt: skip


def settings_tool(settings: SettingsPanes, language: AssistantLanguage) -> Tool:
    texts = _TEXTS[language]

    def run(arguments: dict[str, Any]) -> str:
        try:
            found = settings.open(string_argument(arguments, "pane"))
        except DesktopError as error:
            raise failure(error, language) from error
        return texts["settings_opened" if found else "settings_main"]

    return Tool("openSettings", texts["settings"], run=run, parameters=obj(["pane"], pane=choice(SettingsPane, "")))


def screenshot_tool(
    screenshots: Screenshots,
    folders: Folders,
    language: AssistantLanguage,
    clock: Callable[[], datetime] = datetime.now,
) -> Tool:
    texts = _TEXTS[language]

    def run(arguments: dict[str, Any]) -> str:
        try:
            area = ScreenshotArea(string_argument(arguments, "area") or ScreenshotArea.WHOLE_SCREEN)
        except ValueError:
            area = ScreenshotArea.WHOLE_SCREEN
        try:
            if arguments.get("toClipboard") is True:
                with tempfile.TemporaryDirectory(prefix="bilge-") as scratch:
                    image = Path(scratch) / "screenshot.png"
                    if not screenshots.capture(area, image):
                        return texts["shot_cancelled"]
                    screenshots.copy_image(image)
                return texts["shot_copied"]
            folder = folders.pictures() / texts["shot_folder"]
            folder.mkdir(parents=True, exist_ok=True)
            image = folder / texts["shot_name"].format(stamp=clock().strftime("%Y-%m-%d %H.%M.%S"))
            if not screenshots.capture(area, image):
                return texts["shot_cancelled"]
        except DesktopError as error:
            raise failure(error, language) from error
        except OSError as error:
            raise failure(DesktopError(str(error)), language) from error
        return texts["shot_saved"].format(folder=folder.name)

    parameters = obj(
        area=choice(ScreenshotArea, texts["area"]),
        toClipboard={"type": "boolean", "description": texts["to_clipboard"]},
    )
    return Tool("takeScreenshot", texts["screenshot"], run=run, parameters=parameters)


def system_tools(
    session: Session, network: Network, settings: SettingsPanes, screenshots: Screenshots, folders: Folders,
    language: AssistantLanguage,
) -> list[Tool]:  # fmt: skip
    return [
        system_action_tool(session, language),
        battery_tool(language),
        system_info_tool(network, folders, language),
        wifi_tool(network, language),
        settings_tool(settings, language),
        screenshot_tool(screenshots, folders, language),
    ]
