from collections.abc import Iterable
from dataclasses import dataclass

from bilge.core.language import AssistantLanguage
from bilge.core.speech import spoken_text
from bilge.core.text import levenshtein, normalized


@dataclass(frozen=True)
class WordErrorRate:
    errors: int
    reference_word_count: int

    @property
    def rate(self) -> float:
        if self.reference_word_count == 0:
            return 0.0 if self.errors == 0 else 1.0
        return self.errors / self.reference_word_count

    @classmethod
    def compute(
        cls, reference: str, hypothesis: str, language: AssistantLanguage = AssistantLanguage.TURKISH
    ) -> "WordErrorRate":
        """Both sides are spoken-normalized first so "14:30" and "on dört otuz" count as the same words."""
        reference_words = _words(reference, language)
        hypothesis_words = _words(hypothesis, language)
        return cls(errors=levenshtein(reference_words, hypothesis_words), reference_word_count=len(reference_words))

    @staticmethod
    def aggregate(results: Iterable["WordErrorRate"]) -> float:
        results = list(results)
        words = sum(result.reference_word_count for result in results)
        errors = sum(result.errors for result in results)
        return 0.0 if words == 0 else errors / words


def _words(text: str, language: AssistantLanguage) -> list[str]:
    return normalized(spoken_text.normalize(text, language)).split()
