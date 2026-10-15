"""Rewrites model output into plain text for the synthesizer, in the assistant's language."""

import re

from bilge.core.language import AssistantLanguage
from bilge.core.speech import english_speech_normalizer, turkish_speech_normalizer

# Python's re has no \p{Extended_Pictographic}; these are its ranges from Unicode emoji-data.txt.
_EXTENDED_PICTOGRAPHIC = (
    "©®‼⁉™ℹ↔-↙↩-↪⌚-⌛⌨⎈⏏"
    "⏩-⏳⏸-⏺Ⓜ▪-▫▶◀◻-◾☀-★☇-☒"
    "☔-⚅⚐-✅✈-✒✔✖✝✡✨✳-✴❄❇"
    "❌❎❓-❕❗❣-❧➕-➗➡➰➿⤴-⤵"
    "⬅-⬇⬛-⬜⭐⭕〰〽㊗㊙"
    "\U0001f000-\U0001f0ff\U0001f10d-\U0001f10f\U0001f12f\U0001f16c-\U0001f171\U0001f17e-\U0001f17f"
    "\U0001f18e\U0001f191-\U0001f19a\U0001f1ad-\U0001f1e5\U0001f201-\U0001f20f\U0001f21a\U0001f22f"
    "\U0001f232-\U0001f23a\U0001f23c-\U0001f23f\U0001f249-\U0001f3fa\U0001f400-\U0001f53d"
    "\U0001f546-\U0001f64f\U0001f680-\U0001f6ff\U0001f774-\U0001f77f\U0001f7d5-\U0001f7ff"
    "\U0001f80c-\U0001f80f\U0001f848-\U0001f84f\U0001f85a-\U0001f85f\U0001f888-\U0001f88f"
    "\U0001f8ae-\U0001f8ff\U0001f90c-\U0001f93a\U0001f93c-\U0001f945\U0001f947-\U0001faff"
    "\U0001fc00-\U0001fffd"
)
_REGIONAL_INDICATORS = "\U0001f1e6-\U0001f1ff"

_BOLD_OR_CODE = re.compile(r"\*\*|__|`")
_HEADING_OR_BULLET = re.compile(r"^\s*(#{1,6}|[-*•])\s+", re.MULTILINE)
_EMPHASIS = re.compile(r"(?<![\w*])([*_])(?=\S)(.+?)(?<=\S)\1(?![\w*])")
_EMOJI = re.compile(f"[{_EXTENDED_PICTOGRAPHIC}{_REGIONAL_INDICATORS}️‍⃣]+")


def normalize(text: str, language: AssistantLanguage) -> str:
    if language is AssistantLanguage.ENGLISH:
        return english_speech_normalizer.normalize(text)
    return turkish_speech_normalizer.normalize(text)


def without_markup(text: str) -> str:
    """Markdown and emoji, which conversation models add despite being told not to; TTS would read them out."""
    result = _BOLD_OR_CODE.sub("", text)
    result = _HEADING_OR_BULLET.sub("", result)
    result = _EMPHASIS.sub(r"\2", result)
    return _EMOJI.sub("", result)
