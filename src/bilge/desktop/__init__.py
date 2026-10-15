"""Integration with the operating system's desktop, behind the interfaces in `base`."""

import sys

from bilge.core.language import AssistantLanguage
from bilge.desktop.base import Desktop


def current(language: AssistantLanguage) -> Desktop | None:
    """None where Bilge has no desktop integration yet; the assistant then runs without those tools."""
    if sys.platform.startswith("linux"):
        from bilge.desktop import linux

        # Menu entries are matched in the assistant's language first, then by their untranslated names.
        languages = ("tr_TR", "tr") if language is AssistantLanguage.TURKISH else ("en_US", "en")
        return linux.build(languages)
    return None
