import pytest

from bilge.core.conversation import quick_intent_parser
from bilge.core.conversation.quick_intent_parser import (
    Screenshot,
    Settings,
    SettingsPane,
    SystemInfo,
    SystemInfoTopic,
    Wifi,
    Window,
    WindowAction,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ekran görüntüsü al", Screenshot()),
        ("Wi-Fi'ı kapat", Wifi(on=False)),
        ("wifi aç", Wifi(on=True)),
        ("Wi-Fi'yi açar mısın", Wifi(on=True)),
        ("pencereyi küçült", Window(WindowAction.MINIMIZE)),
        ("tam ekran yap", Window(WindowAction.FULL_SCREEN)),
        ("pencereyi ekranın soluna al", Window(WindowAction.LEFT_HALF)),
        ("diğer uygulamaları gizle", Window(WindowAction.HIDE_OTHERS)),
        ("Bluetooth ayarlarını aç", Settings(SettingsPane.BLUETOOTH)),
        ("yazılım güncelleme ayarlarını aç", Settings(SettingsPane.SOFTWARE_UPDATE)),
        ("bildirim ayarlarına git", Settings(SettingsPane.NOTIFICATIONS)),
        ("diskte ne kadar yer kaldı", SystemInfo(SystemInfoTopic.DISK)),
        ("bilgisayar ne zamandır açık", SystemInfo(SystemInfoTopic.UPTIME)),
        ("IP adresim ne", SystemInfo(SystemInfoTopic.NETWORK)),
    ],
)
def test_recognizes_mac_controls(text, expected):
    assert quick_intent_parser.parse(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "bu pencerenin ekran görüntüsünü panoya al",
        "Wi-Fi'ı kapat ve müziği aç",
        "küçült",
        "Safari'yi gizle",
        "ses ayarlarını kıs",
        "Telegram ayarlarını aç",
    ],
)
def test_leaves_anything_with_more_content_to_the_model(text):
    assert quick_intent_parser.parse(text) is None
