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
    return Tool("currentDateTime", description, run=lambda _: spoken_now(clock(), language))
