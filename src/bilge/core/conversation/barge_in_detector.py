"""Decides whether speech heard while the assistant is talking is the user cutting in.
Echo cancellation is never perfect, so words the assistant is currently saying are removed
before looking for the wake phrase or a stop word."""

from dataclasses import dataclass

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded
from bilge.core.wake.wake_phrase_matcher import WakePhraseMatcher


@dataclass(frozen=True)
class NoBargeIn:
    pass


@dataclass(frozen=True)
class Stop:
    pass


@dataclass(frozen=True)
class Command:
    command: str


Decision = NoBargeIn | Stop | Command

_TURKISH_STOP_WORDS = frozenset(
    {"dur", "durdur", "sus", "yeter", "kes", "tamam", "iptal", "hayir", "bekle", "stop", "artik"}
)
_ENGLISH_STOP_WORDS = frozenset(
    {"stop", "quiet", "enough", "cancel", "wait", "hush", "silence", "okay", "ok", "no", "please", "now"}
)
# Filler words such as "artık" or "please" end a stop only together with a real stop word.
_FILLER_ONLY = frozenset({"artik", "please", "now"})
_MAX_STOP_UTTERANCE_WORDS = 4


class BargeInDetector:
    def __init__(self, matcher: WakePhraseMatcher, language: AssistantLanguage = AssistantLanguage.TURKISH) -> None:
        self.matcher = matcher
        self._stop_words = _ENGLISH_STOP_WORDS if language is AssistantLanguage.ENGLISH else _TURKISH_STOP_WORDS

    def evaluate(self, heard: str, speaking: str) -> Decision:
        echo_words = set(folded(speaking).split())
        # Drop every word the assistant is saying right now; its own "Tamam" or "Ben Bilge" must
        # not cut it off. The user's words that differ from the reply are what remains.
        remaining = [word for word in heard.split() if (key := folded(word)) and key not in echo_words]
        if not remaining:
            return NoBargeIn()

        match = self.matcher.match(" ".join(remaining))
        if match is not None:
            rest = folded(match.command).split()
            if all(word in self._stop_words for word in rest):
                return Stop()
            return Command(match.command)
        keys = [folded(word) for word in remaining]
        if len(keys) <= _MAX_STOP_UTTERANCE_WORDS and any(self._is_stop(key) for key in keys):
            return Stop()
        return NoBargeIn()

    def _is_stop(self, key: str) -> bool:
        return key in self._stop_words and key not in _FILLER_ONLY
