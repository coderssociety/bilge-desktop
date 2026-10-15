"""The day at a glance, put into a few spoken sentences, and the requests that ask for it."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo

from bilge.core.identity import DEFAULT_WAKE_PHRASE
from bilge.core.language import AssistantLanguage
from bilge.core.text import folded, time_locative

# "Günün özeti" and the first "günaydın" of the day.
_PHRASES = (
    "gunun ozeti",
    "gunu ozetle",
    "bugun neler var",
    "sabah ozeti",
    "gunluk ozet",
    "bugun beni neler bekliyor",
    "brifing",
    "bugunun ozeti",
)
_ENGLISH_PHRASES = (
    "daily briefing",
    "morning briefing",
    "brief me",
    "summary of my day",
    "summary of the day",
    "my day look like",
    "my day like",
    "todays summary",
    "plan for today",
)

_TURKISH_MONTHS = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)  # fmt: skip
_TURKISH_WEEKDAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
_ENGLISH_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
_ENGLISH_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# Newer ICU puts a narrow no-break space before AM/PM, which the Swift version's tests expect.
_NARROW_NO_BREAK_SPACE = " "

_MORNING_START, _AFTERNOON_START, _EVENING_START = 5, 12, 18
_LISTED_EVENTS = 3
_LISTED_REMINDERS = 2


def is_request(text: str, language: AssistantLanguage = AssistantLanguage.TURKISH) -> bool:
    text = folded(text)
    phrases = _ENGLISH_PHRASES if language is AssistantLanguage.ENGLISH else _PHRASES
    return any(phrase in text for phrase in phrases)


def is_morning_greeting(
    text: str, wake_phrase: str = DEFAULT_WAKE_PHRASE, language: AssistantLanguage = AssistantLanguage.TURKISH
) -> bool:
    """ "Günaydın" with nothing else to ask; "günaydın, saat kaç" is a question."""
    wake = folded(wake_phrase)
    words = [word for word in folded(text).split() if word != wake]
    return words == (["good", "morning"] if language is AssistantLanguage.ENGLISH else ["gunaydin"])


@dataclass(frozen=True)
class DailyBriefing:
    """Missing parts (no weather, no mail access) are simply left out."""

    @dataclass(frozen=True)
    class Event:
        title: str
        start: datetime

    now: datetime
    weather: str | None
    # Today's timed events still ahead, in order.
    events: Sequence["DailyBriefing.Event"]
    # Reminders due today or overdue.
    reminders: Sequence[str]
    # None when it could not be checked.
    unread_mail: int | None

    def text(self, tz: tzinfo | None = None, language: AssistantLanguage = AssistantLanguage.TURKISH) -> str:
        """`tz` plays the role of Swift's Calendar: None means the system's local time."""
        if language is AssistantLanguage.ENGLISH:
            return self._english_text(tz)
        now = _local(self.now, tz)
        date = f"{now.day} {_TURKISH_MONTHS[now.month - 1]} {_TURKISH_WEEKDAYS[now.weekday()]}"
        sentences = [_turkish_greeting(now.hour), f"Bugün {date}."]
        if self.weather is not None:
            sentences.append(self.weather)
        sentences.append(self._events_sentence(tz))
        reminders = self._reminders_sentence()
        if reminders is not None:
            sentences.append(reminders)
        if self.unread_mail is not None and self.unread_mail > 0:
            sentences.append(f"{self.unread_mail} okunmamış e-postan var.")
        return " ".join(sentences)

    def _events_sentence(self, tz: tzinfo | None) -> str:
        if not self.events:
            return "Bugün başka etkinliğin yok."
        listed = []
        for event in self.events[:_LISTED_EVENTS]:
            start = _local(event.start, tz)
            listed.append(f"{time_locative(start.hour, start.minute)} {event.title}")
        return f"Bugün {len(self.events)} etkinliğin var: {_list(listed, len(self.events))}."

    def _reminders_sentence(self) -> str | None:
        if not self.reminders:
            return None
        if len(self.reminders) == 1:
            return f"Bugünkü anımsatıcın: {self.reminders[0]}."
        listed = list(self.reminders[:_LISTED_REMINDERS])
        return f"{len(self.reminders)} anımsatıcın var: {_list(listed, len(self.reminders))}."

    def _english_text(self, tz: tzinfo | None) -> str:
        now = _local(self.now, tz)
        date = f"{_ENGLISH_WEEKDAYS[now.weekday()]}, {_ENGLISH_MONTHS[now.month - 1]} {now.day}"
        sentences = [_english_greeting(now.hour), f"Today is {date}."]
        if self.weather is not None:
            sentences.append(self.weather)
        sentences.append(self._english_events_sentence(tz))
        if len(self.reminders) == 1:
            sentences.append(f"Today's reminder: {self.reminders[0]}.")
        elif len(self.reminders) > 1:
            listed = list(self.reminders[:_LISTED_REMINDERS])
            sentences.append(f"You have {len(self.reminders)} reminders: {_english_list(listed, len(self.reminders))}.")
        if self.unread_mail is not None and self.unread_mail > 0:
            noun = "email" if self.unread_mail == 1 else "emails"
            sentences.append(f"You have {self.unread_mail} unread {noun}.")
        return " ".join(sentences)

    def _english_events_sentence(self, tz: tzinfo | None) -> str:
        if not self.events:
            return "You have nothing else on your calendar today."
        listed = [
            f"{event.title} at {_english_time(_local(event.start, tz))}" for event in self.events[:_LISTED_EVENTS]
        ]
        noun = "event" if len(self.events) == 1 else "events"
        return f"You have {len(self.events)} {noun} today: {_english_list(listed, len(self.events))}."


def _local(moment: datetime, tz: tzinfo | None) -> datetime:
    if tz is None and moment.tzinfo is None:
        return moment
    return moment.astimezone(tz)


def _turkish_greeting(hour: int) -> str:
    if _MORNING_START <= hour < _AFTERNOON_START:
        return "Günaydın."
    if _AFTERNOON_START <= hour < _EVENING_START:
        return "İyi günler."
    return "İyi akşamlar."


def _english_greeting(hour: int) -> str:
    if _MORNING_START <= hour < _AFTERNOON_START:
        return "Good morning."
    if _AFTERNOON_START <= hour < _EVENING_START:
        return "Good afternoon."
    return "Good evening."


def _english_time(moment: datetime) -> str:
    """ "9:30 AM", as the en_US shortened time style writes it."""
    hour = moment.hour % 12 or 12
    meridiem = "AM" if moment.hour < 12 else "PM"
    return f"{hour}:{moment.minute:02d}{_NARROW_NO_BREAK_SPACE}{meridiem}"


def _english_list(items: list[str], total: int) -> str:
    """ "a, b, c and 3 more"."""
    rest = total - len(items)
    if rest > 0:
        return ", ".join(items) + f" and {rest} more"
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]


def _list(items: list[str], total: int) -> str:
    """ "a, b, c ve 3 tane daha"."""
    rest = total - len(items)
    return ", ".join(items) + f" ve {rest} tane daha" if rest > 0 else ", ".join(items)
