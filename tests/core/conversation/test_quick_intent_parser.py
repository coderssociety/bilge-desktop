import pytest

from bilge.core.conversation import quick_intent_parser
from bilge.core.conversation.quick_intent_parser import (
    Battery,
    Calculate,
    Calendar,
    CalendarRange,
    Clipboard,
    DateTime,
    Folder,
    Media,
    MediaAction,
    OpenApp,
    OpenFolder,
    QuickIntent,
    QuitApp,
    Reminders,
    SetVolume,
    System,
    SystemAction,
    Timer,
    TimerAction,
    Timers,
    Volume,
    VolumeStep,
)
from bilge.core.speech import turkish_number_parser, turkish_time_of_day


def parse(text: str) -> QuickIntent | None:
    return quick_intent_parser.parse(turkish_time_of_day.resolve(turkish_number_parser.digitize(text)))


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("Saat kaç", DateTime()),
        ("saat kaç oldu acaba", DateTime()),
        ("Bugün günlerden ne", DateTime()),
        ("ayın kaçı", DateTime()),
        ("Pil durumu nedir", Battery()),
        ("şarjım ne kadar", Battery()),
        ("Sesi yüzde otuz yap", Volume(SetVolume(30))),
        ("sesi elliye getir", Volume(SetVolume(50))),
        ("Sesi biraz kıs", Volume(VolumeStep.DOWN)),
        ("sesi yükselt", Volume(VolumeStep.UP)),
        ("Sesi kapat", Volume(VolumeStep.MUTE)),
        ("Müziği durdur", Media(MediaAction.PAUSE)),
        ("müziği başlat", Media(MediaAction.PLAY)),
        ("Sonraki şarkıya geç", Media(MediaAction.NEXT)),
        ("şarkıyı geç", Media(MediaAction.NEXT)),
        ("Bir önceki şarkıyı çal", Media(MediaAction.PREVIOUS)),
        ("Bu şarkının adı ne", Media(MediaAction.NOW_PLAYING)),
        ("Ekranı kilitle", System(SystemAction.LOCK_SCREEN)),
        ("Mac'i kilitle", System(SystemAction.LOCK_SCREEN)),
        ("Bilgisayarı uyut", System(SystemAction.SLEEP)),
        ("Karanlık modu aç", System(SystemAction.DARK_MODE_ON)),
        ("aydınlık moda geç", System(SystemAction.DARK_MODE_OFF)),
        ("Bugün takvimde ne var", Calendar(CalendarRange.TODAY)),
        ("Yarın takvimimde ne var", Calendar(CalendarRange.TOMORROW)),
        ("Bu hafta neler var", Calendar(CalendarRange.THIS_WEEK)),
        ("Anımsatıcılarımı oku", Reminders()),
        ("Yüz yirminin yarısı kaç", Calculate("120 / 2")),
        ("on iki çarpı on beş", Calculate("12 * 15")),
        ("On dakikalık zamanlayıcı kur", Timer(seconds=600)),
        ("beş dakika sonra beni uyar", Timer(seconds=300)),
        ("Safari'yi aç", OpenApp("Safari'yi")),
        ("hesap makinesini açar mısın", OpenApp("hesap makinesini")),
        ("Spotify uygulamasını kapat", QuitApp("Spotify")),
        ("Terminali kapat", QuitApp("Terminali")),
        ("Ekranı kilitler misin", System(SystemAction.LOCK_SCREEN)),
        ("Karanlık moda geçer misin", System(SystemAction.DARK_MODE_ON)),
        ("Şu an saat kaç acaba", DateTime()),
        ("Xcode'u açar mısın lütfen", OpenApp("Xcode'u")),
        ("müziği durdurur musun", Media(MediaAction.PAUSE)),
        ("Yarım saat sonra beni uyar", Timer(seconds=1800)),
        ("çeyrek saatlik zamanlayıcı kur", Timer(seconds=900)),
        ("Belgeler klasörünü aç", OpenFolder(Folder.DOCUMENTS)),
        ("İndirilenleri aç", OpenFolder(Folder.DOWNLOADS)),
        ("masaüstünü açar mısın", OpenFolder(Folder.DESKTOP)),
        ("Bütün alarmları kapat", Timers(TimerAction.CANCEL_ALL)),
        ("zamanlayıcıları iptal et", Timers(TimerAction.CANCEL_ALL)),
        ("kurulu zamanlayıcılar neler", Timers(TimerAction.LIST)),
        ("Kopyaladığım metni okur musun", Clipboard()),
        ("panodaki yazıyı oku", Clipboard()),
    ],
)
def test_recognizes_everyday_commands_without_the_model(command, expected):
    assert parse(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "Yirmi dakika sonra çayı hatırlat",  # has a label
        "Yarın saat onda diş hekimi randevusu ekle",  # writes to calendar
        "İndirilenler klasöründeki faturayı aç",  # a file, not the folder
        "Masaüstündeki deneme dosyasını aç",
        "alarmları kapat ve müziği aç",
        "kopyaladığım metni Notlar'a yapıştır",
        "Rahatsız etme modunu aç",  # Focus goes through Shortcuts
        "Sesi biraz aç ve müziği başlat",  # two actions
        "Türkiye'nin başkenti neresi",
        "Bluetooth'u kapat",
        "Bilgisayarı kapat",
        "ondan sonra müziği aç",
        "Saat kaçta toplantım var",
    ],
)
def test_leaves_anything_unusual_or_richer_to_the_model(command):
    assert parse(command) is None
