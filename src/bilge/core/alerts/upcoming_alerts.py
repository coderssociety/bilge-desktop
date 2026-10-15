"""Decides what the assistant says without being asked: calendar events shortly before they start,
reminders when their time comes."""

import math
from collections.abc import Iterable, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from bilge.core.language import AssistantLanguage

# An event that started this recently still counts as "starting now".
_STARTED_TOLERANCE = timedelta(seconds=60)
_SECONDS_PER_MINUTE = 60


@dataclass(frozen=True)
class AlertCandidate:
    class Kind(Enum):
        EVENT = "event"
        REMINDER = "reminder"

    # Identifies the item at this time, so a rescheduled event is announced again.
    key: str
    title: str
    date: datetime
    kind: "AlertCandidate.Kind"


def due(
    candidates: Iterable[AlertCandidate],
    now: datetime,
    lead: timedelta,
    grace: timedelta,
    announced: Set[str],
) -> list[AlertCandidate]:
    def is_due(candidate: AlertCandidate) -> bool:
        offset = candidate.date - now
        if candidate.kind is AlertCandidate.Kind.EVENT:
            return -_STARTED_TOLERANCE <= offset <= lead
        return -grace <= offset <= timedelta(0)

    pending = (candidate for candidate in candidates if candidate.key not in announced)
    return sorted((candidate for candidate in pending if is_due(candidate)), key=lambda candidate: candidate.date)


def message(
    alerts: Iterable[AlertCandidate], now: datetime, language: AssistantLanguage = AssistantLanguage.TURKISH
) -> str:
    return " ".join(_sentence(alert, now, language) for alert in alerts)


def _sentence(alert: AlertCandidate, now: datetime, language: AssistantLanguage) -> str:
    minutes = math.ceil((alert.date - now).total_seconds() / _SECONDS_PER_MINUTE)
    is_reminder = alert.kind is AlertCandidate.Kind.REMINDER
    if language is AssistantLanguage.ENGLISH:
        if is_reminder:
            return f"Reminder: {alert.title}."
        return f"{alert.title} is starting now." if minutes <= 1 else f"{alert.title} starts in {minutes} minutes."
    if is_reminder:
        return f"Hatırlatma: {alert.title}."
    return f"{alert.title} şimdi başlıyor." if minutes <= 1 else f"{minutes} dakika sonra {alert.title} var."
