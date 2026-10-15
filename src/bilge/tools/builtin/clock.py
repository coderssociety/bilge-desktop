from collections.abc import Callable
from datetime import datetime

from bilge.brain.instructions import spoken_now
from bilge.core.language import AssistantLanguage
from bilge.tools.base import Tool


def current_date_time(language: AssistantLanguage, clock: Callable[[], datetime] = datetime.now) -> Tool:
    description = (
        "Returns the current date, weekday and time on this computer."
        if language is AssistantLanguage.ENGLISH
        else "Bu bilgisayardaki şu anki tarihi, haftanın gününü ve saati verir."
    )

    def run(_: dict) -> str:
        now = clock()
        date = spoken_now(now, language).rsplit(" ", 1)[0].rstrip(",")
        if language is AssistantLanguage.ENGLISH:
            return f"It's {now:%H:%M}, {date}."
        return f"Saat {now:%H:%M}. Bugün {date}."

    return Tool("currentDateTime", description, run=run)
