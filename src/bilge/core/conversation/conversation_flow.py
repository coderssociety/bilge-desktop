"""Pure turn-taking logic: when to wake, when a transcript is a command, and when to go back to sleep."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from bilge.core.text import folded
from bilge.core.wake.wake_phrase_matcher import WakePhraseMatcher


@dataclass(frozen=True)
class ListeningForWake:
    pass


@dataclass(frozen=True)
class AwaitingCommand:
    deadline: datetime


@dataclass(frozen=True)
class Processing:
    pass


@dataclass(frozen=True)
class Responding:
    pass


@dataclass(frozen=True)
class FollowUp:
    deadline: datetime


Phase = ListeningForWake | AwaitingCommand | Processing | Responding | FollowUp


@dataclass(frozen=True)
class NoAction:
    pass


@dataclass(frozen=True)
class AcknowledgeWake:
    pass


@dataclass(frozen=True)
class RunCommand:
    command: str


@dataclass(frozen=True)
class RunWorkInput:
    """Said during a work session without the wake phrase: input for that work (a cell edit, text
    to type) rather than a command to the assistant."""

    text: str


@dataclass(frozen=True)
class ReturnToIdle:
    timed_out: bool


Action = NoAction | AcknowledgeWake | RunCommand | RunWorkInput | ReturnToIdle


@dataclass(frozen=True)
class WorkSession:
    """A stretch of hands-free work, such as editing a spreadsheet: the window stays open longer, and
    without the wake phrase only what `accepts` recognizes is taken as a command, so talk in the
    room is not acted on."""

    window: float
    accepts: Callable[[str], bool]


# Both languages' phrases: none of them means anything else in the other language.
_CANCEL_PHRASES = frozenset(
    {
        "iptal", "iptal et", "vazgec", "vazgectim", "bos ver", "bosver", "bir sey yok", "yok bir sey", "unut gitsin",
        "cancel", "never mind", "nevermind", "forget it",
    }
)  # fmt: skip
# Also end a window, but are ordinary words while dictating, so a work session takes them as input.
_OUTSIDE_WORK_CANCEL_PHRASES = frozenset(
    {"nothing", "that s all", "thats all", "stop", "stop it", "be quiet", "quiet", "shut up", "enough"}
)


def _cancels(key: str, in_work: bool) -> bool:
    return key in _CANCEL_PHRASES or (not in_work and key in _OUTSIDE_WORK_CANCEL_PHRASES)


class ConversationFlow:
    def __init__(self, matcher: WakePhraseMatcher, command_timeout: float = 6, follow_up_window: float = 6) -> None:
        self.matcher = matcher
        self.command_timeout = command_timeout
        self.follow_up_window = follow_up_window
        self._phase: Phase = ListeningForWake()
        self._session: WorkSession | None = None
        self._speech_in_progress = False

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def is_awaiting_speech(self) -> bool:
        return isinstance(self._phase, AwaitingCommand | FollowUp)

    def heard(self, transcript: str, at: datetime) -> Action:
        self._speech_in_progress = False
        if isinstance(self._phase, ListeningForWake):
            return self._heard_while_idle(transcript, at)
        if isinstance(self._phase, AwaitingCommand | FollowUp):
            return self._heard_in_window(transcript)
        return NoAction()

    def _heard_while_idle(self, transcript: str, now: datetime) -> Action:
        match = self.matcher.match(transcript)
        if match is None:
            return NoAction()
        if not match.command:
            self._phase = AwaitingCommand(deadline=now + timedelta(seconds=self.command_timeout))
            return AcknowledgeWake()
        # "Bilge, stop" while nothing is going on has nothing to stop; it is not a command to route.
        if _cancels(folded(match.command), in_work=False):
            return NoAction()
        return self._run(match.command)

    def _heard_in_window(self, transcript: str) -> Action:
        wake_match = self.matcher.match(transcript)
        command = wake_match.command if wake_match is not None else transcript.strip()
        key = folded(command)
        if not key:
            return NoAction()
        session = self._session
        if (
            isinstance(self._phase, FollowUp)
            and session is not None
            and wake_match is None
            and not _cancels(key, in_work=True)
        ):
            if not session.accepts(command):
                return NoAction()
            self._phase = Processing()
            return RunWorkInput(command)
        if _cancels(key, in_work=False):
            self._session = None
            self._phase = ListeningForWake()
            return ReturnToIdle(timed_out=False)
        return self._run(command)

    def speech_started(self, at: datetime) -> None:
        """Once the user starts talking inside a window, the deadline no longer cuts them off."""
        if self.is_awaiting_speech:
            self._speech_in_progress = True

    def tick(self, at: datetime) -> Action:
        if self._speech_in_progress:
            return NoAction()
        phase = self._phase
        if isinstance(phase, AwaitingCommand) and at >= phase.deadline:
            self._phase = ListeningForWake()
            return ReturnToIdle(timed_out=True)
        if isinstance(phase, FollowUp) and at >= phase.deadline:
            self._session = None
            self._phase = ListeningForWake()
            return ReturnToIdle(timed_out=False)
        return NoAction()

    def response_started(self) -> None:
        self._phase = Responding()

    def response_finished(self, at: datetime, allow_follow_up: bool, session: WorkSession | None = None) -> None:
        self._speech_in_progress = False
        self._session = session
        if session is not None:
            self._phase = FollowUp(deadline=at + timedelta(seconds=session.window))
        elif allow_follow_up:
            self._phase = FollowUp(deadline=at + timedelta(seconds=self.follow_up_window))
        else:
            self._phase = ListeningForWake()

    def reset(self) -> None:
        """Abandons whatever is happening (errors, user stop) and listens for the wake phrase again."""
        self._speech_in_progress = False
        self._session = None
        self._phase = ListeningForWake()

    def _run(self, command: str) -> Action:
        self._phase = Processing()
        return RunCommand(command)
