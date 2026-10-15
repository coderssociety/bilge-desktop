from datetime import UTC, datetime, timedelta

from bilge.core.alerts import upcoming_alerts
from bilge.core.alerts.upcoming_alerts import AlertCandidate

NOW = datetime.fromtimestamp(1_800_000_000, UTC)
LEAD = timedelta(minutes=10)
GRACE = timedelta(minutes=5)


def event(title: str, in_minutes: float) -> AlertCandidate:
    return AlertCandidate(f"e-{title}", title, NOW + timedelta(minutes=in_minutes), AlertCandidate.Kind.EVENT)


def reminder(title: str, in_minutes: float) -> AlertCandidate:
    return AlertCandidate(f"r-{title}", title, NOW + timedelta(minutes=in_minutes), AlertCandidate.Kind.REMINDER)


def test_announces_events_starting_within_the_lead_time_not_later_ones_or_ones_long_started() -> None:
    candidates = [event("Toplantı", 9), event("Akşam yemeği", 45), event("Sabah koşusu", -20)]
    due = upcoming_alerts.due(candidates, now=NOW, lead=LEAD, grace=GRACE, announced=set())
    assert [alert.title for alert in due] == ["Toplantı"]


def test_announces_reminders_whose_time_has_come_within_the_grace_period() -> None:
    candidates = [reminder("İlaç", -1), reminder("Süt", 3), reminder("Eski", -30)]
    due = upcoming_alerts.due(candidates, now=NOW, lead=LEAD, grace=GRACE, announced=set())
    assert [alert.title for alert in due] == ["İlaç"]


def test_never_announces_the_same_item_twice_sorted_by_time() -> None:
    candidates = [event("B", 8), event("A", 2)]
    due = upcoming_alerts.due(candidates, now=NOW, lead=LEAD, grace=GRACE, announced={"e-B"})
    assert [alert.title for alert in due] == ["A"]


def test_speaks_minutes_until_an_event_or_that_it_is_starting() -> None:
    assert upcoming_alerts.message([event("Toplantı", 9.2)], now=NOW) == "10 dakika sonra Toplantı var."
    assert upcoming_alerts.message([event("Toplantı", 0.5)], now=NOW) == "Toplantı şimdi başlıyor."
    assert upcoming_alerts.message([reminder("İlacını al", 0)], now=NOW) == "Hatırlatma: İlacını al."
    assert upcoming_alerts.message([event("A", 5), reminder("B", 0)], now=NOW) == "5 dakika sonra A var. Hatırlatma: B."
