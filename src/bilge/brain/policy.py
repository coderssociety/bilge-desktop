"""Which tool calls may run, which need a spoken yes and which are refused.

Once text someone else may have written enters the conversation (a web page, an e-mail, the clipboard), it is
treated as possibly hostile: it could carry instructions aimed at the model. From then on tools that could carry
that text off the computer are refused, and every other tool with side effects needs a spoken yes, even ones
that are normally safe. Read-only tools stay free: they only bring more data in.

Text read in an earlier turn is further away: only the spoken reply stays in the conversation, and the user
has just asked for something new. Tools that could carry data out then ask first instead of being refused,
and the question shows the arguments, so an address stuffed with data is visible before it is opened.
"""

from dataclasses import dataclass
from enum import Enum

from bilge.tools.base import Risk

# Could send the text somewhere (a URL with data in it, another app) or keep it: an injected "fact" in memory
# would sit in every future conversation's instructions.
REFUSED_AFTER_UNTRUSTED = frozenset({"readWebPage", "openWebsite", "searchWeb", "typeText", "remember", "sendEmail"})
FREE_AFTER_UNTRUSTED = frozenset(
    {
        "currentDateTime", "calculate", "batteryStatus", "systemInfo", "weather", "exchangeRate", "news",
        "readDocument", "readNotes", "readScreen", "readSelection", "readClipboard", "readCalendar",
        "readReminders", "findContact", "readMail", "listShortcuts", "listRunningApps", "listMemories",
    }
)  # fmt: skip


class Action(Enum):
    RUN = "run"
    CONFIRM = "confirm"
    REFUSE = "refuse"


@dataclass(frozen=True)
class Verdict:
    action: Action
    # Said before the question when the step follows untrusted content.
    cautioned: bool = False


def decide(name: str, risk: Risk, read_untrusted: bool, read_earlier: bool = False) -> Verdict:
    """`read_untrusted`: this request already read such text; `read_earlier`: an earlier turn did."""
    if risk is Risk.DISABLED:
        return Verdict(Action.REFUSE)
    if read_untrusted and name in REFUSED_AFTER_UNTRUSTED:
        return Verdict(Action.REFUSE)
    if (read_untrusted or read_earlier) and name not in FREE_AFTER_UNTRUSTED:
        return Verdict(Action.CONFIRM, cautioned=True)
    return Verdict(Action.CONFIRM if risk is Risk.CONFIRM else Action.RUN)
