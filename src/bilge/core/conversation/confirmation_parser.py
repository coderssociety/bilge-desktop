"""Interprets the user's spoken answer to "…yapayım mı?" / "Shall I…?". Errs toward UNCLEAR: an
irreversible action must only run on a clear yes. Each language has its own words; mixing them would
let a folded Turkish word ("süre" → "sure") read as an English yes."""

from dataclasses import dataclass
from enum import StrEnum

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded


class Answer(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class _Words:
    yes: frozenset[str]
    no: frozenset[str]
    # For sending messages: casual words ("tamam", "okay") from a TV or another person in the room
    # must not be enough.
    strict_yes: frozenset[str]
    no_phrases: tuple[str, ...]


_TURKISH = _Words(
    yes=frozenset(
        {
            "evet", "olur", "tamam", "onayliyorum", "onayla", "onay", "gonder", "yap", "tabii", "tabi", "aynen",
            "kesinlikle", "elbette", "peki", "devam", "sil", "ekle", "calistir",
        }
    ),
    no=frozenset(
        {
            "hayir", "iptal", "vazgec", "vazgectim", "yok", "istemiyorum", "dur", "durdur", "yapma", "gonderme",
            "silme", "ekleme", "calistirma", "bosver", "olmaz",
        }
    ),
    strict_yes=frozenset({"evet", "onayliyorum", "onayla", "gonder"}),
    no_phrases=("bos ver", "gerek yok"),
)  # fmt: skip

_ENGLISH = _Words(
    yes=frozenset(
        {
            "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed", "send", "ahead", "proceed",
            "absolutely", "definitely", "certainly", "delete", "add", "run",
        }
    ),
    # Hesitation counts as no: "I'm not sure" or "wait" must never run the action.
    no=frozenset(
        {
            "no", "nope", "nah", "cancel", "stop", "dont", "abort", "negative", "never", "not", "cant", "wont", "wait",
            "hold", "hang", "later", "maybe", "unsure",
        }
    ),
    strict_yes=frozenset({"yes", "confirm", "confirmed", "send"}),
    no_phrases=("never mind", "not now", "forget it", "do not"),
)  # fmt: skip


def parse(text: str, strict: bool = False, language: AssistantLanguage = AssistantLanguage.TURKISH) -> Answer:
    table = _ENGLISH if language is AssistantLanguage.ENGLISH else _TURKISH
    key = folded(text)
    words = set(key.split())
    says_no = not words.isdisjoint(table.no) or any(phrase in key for phrase in table.no_phrases)
    says_yes = not words.isdisjoint(table.strict_yes if strict else table.yes)
    if says_yes and not says_no:
        return Answer.CONFIRMED
    if says_no and not says_yes:
        return Answer.REJECTED
    return Answer.UNCLEAR
