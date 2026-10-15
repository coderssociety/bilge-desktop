"""The always-on voice loop: microphone → speech detection → utterances → recognition → wake word and
conversation flow → the agent → spoken reply.

While a reply is being prepared the microphone is ignored. While it is spoken, the echo-cancelled microphone is
only listened to for the user cutting in ("Bilge, dur" or a new request).
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import numpy as np

from bilge.brain.agent import Agent
from bilge.core.audio.speech_segmenter import Configuration, SpeechSegmenter
from bilge.core.conversation import confirmation_parser
from bilge.core.conversation.barge_in_detector import BargeInDetector, Command, Stop
from bilge.core.conversation.confirmation_parser import Answer
from bilge.core.conversation.conversation_flow import (
    AcknowledgeWake,
    ConversationFlow,
    ListeningForWake,
    NoAction,
    ReturnToIdle,
    RunCommand,
    RunWorkInput,
)
from bilge.core.language import AssistantLanguage
from bilge.core.speaker.voice_print import Decision
from bilge.core.text import folded, similarity
from bilge.core.wake.wake_phrase_matcher import WakePhraseMatcher
from bilge.voice.recognizers import Recognizer
from bilge.voice.speaker import SpeakerGate
from bilge.voice.speech_output import SpeechOutput, tone
from bilge.voice.vad import CHUNK, SAMPLE_RATE, SileroVAD

log = logging.getLogger(__name__)

WAKE_PROBE_SECONDS = 2.5
# How close the full model's first word must be to the wake word to be taken as its spelling.
WAKE_SPELLING_SIMILARITY = 0.4
# Looser still for cut-ins: the full model checks what was said, this only decides whether to ask it.
CUT_IN_GATE_SIMILARITY = 0.5
TICK_SECONDS = 0.25
CONFIRMATION_TIMEOUT = 8.0
# Someone mid-sentence gets a little longer before the question lapses.
CONFIRMATION_GRACE = 5.0


class Status(StrEnum):
    OFF = "off"
    LISTENING = "listening"
    AWAKE = "awake"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    CONFIRMING = "confirming"


@dataclass(frozen=True)
class Options:
    wake_phrase: str = "bilge"
    follow_up: bool = True
    barge_in: bool = True


EventHandler = Callable[[str, str], None]


class VoiceAssistant:
    def __init__(
        self,
        recognizer: Recognizer,
        speech: SpeechOutput,
        agent: Agent,
        language: AssistantLanguage,
        options: Options | None = None,
        speaker_gate: SpeakerGate | None = None,
        on_event: EventHandler | None = None,
        wake_recognizer: Recognizer | None = None,
    ):
        self.recognizer = recognizer
        # A small, fast model for the wake word and cut-ins; the full one only for what is then said. The wake
        # word is Turkish in both languages, so the small model should listen in Turkish.
        self.wake_recognizer = wake_recognizer or recognizer
        self.speech = speech
        self.agent = agent
        self.language = language
        self.options = options or Options()
        self.speaker_gate = speaker_gate
        self._on_event = on_event or (lambda kind, text: None)
        self.matcher = WakePhraseMatcher(self.options.wake_phrase)
        self.flow = ConversationFlow(self.matcher)
        self._flow_lock = threading.RLock()
        self._vad = SileroVAD()
        self._segmenter = SpeechSegmenter(Configuration(chunk_duration=CHUNK / SAMPLE_RATE, min_silence=0.6))
        # Stricter while Bilge talks: what is left of its own voice must not open an utterance on its own.
        self._barge_segmenter = SpeechSegmenter(
            Configuration(chunk_duration=CHUNK / SAMPLE_RATE, start_threshold=0.75, end_threshold=0.4,
                          min_silence=0.45, pre_roll=0.3, min_speech=0.3, max_segment=3)
        )  # fmt: skip
        self._barge_detector = BargeInDetector(self.matcher, language)
        self._utterances: list[np.ndarray] = []
        self._barge_utterances: list[np.ndarray] = []
        self._wake = threading.Condition()
        self._suspended = False
        self._speaking = False
        self._thinking = False
        self._reply_so_far = ""
        self._pending_answer: Answer | None = None
        self._awaiting_answer = threading.Event()
        self._answered = threading.Event()
        self._stopped_by_user = False
        self._asking = False
        self._last_heard = ""
        self._barge_command: str | None = None
        self._running = threading.Event()
        # Set by stop(); the ticker sleeps on it so stopping wakes it at once.
        self._stopping = threading.Event()
        self._turn: threading.Thread | None = None
        self.status = Status.OFF

    # MARK: - Lifecycle

    def start(self) -> None:
        self._stopping.clear()
        self._running.set()
        with self._flow_lock:
            self.flow.reset()
        for target, name in [(self._process_utterances, "bilge-utterances"), (self._process_barge_ins, "bilge-barge-in"),
                             (self._tick, "bilge-tick")]:  # fmt: skip
            threading.Thread(target=target, name=name, daemon=True).start()
        self._set_status(Status.LISTENING)

    def stop(self) -> None:
        self._running.clear()
        self._stopping.set()
        self._resolve(Answer.REJECTED)
        self.speech.stop()
        with self._wake:
            self._wake.notify_all()
        self._set_status(Status.OFF)

    def interrupt(self) -> None:
        """Stops the reply in progress; Bilge keeps listening."""
        self._resolve(Answer.REJECTED)
        self.speech.stop()

    # MARK: - Audio (called on the audio thread for each 512-sample chunk)

    def on_chunk(self, chunk: np.ndarray) -> None:
        probability = self._vad.probability(chunk)
        samples = chunk.tolist()
        if self._suspended:
            # While Bilge thinks or talks, the user can still stop it or ask something else.
            if (self._speaking or self._thinking) and self.options.barge_in:
                for segment in self._barge_segmenter.process(samples, probability):
                    log.debug("Cut-in segment: %.1f s", len(segment.samples) / SAMPLE_RATE)
                    self._queue(self._barge_utterances, np.asarray(segment.samples, dtype=np.float32))
            return
        was_in_speech = self._segmenter.is_in_speech
        segments = self._segmenter.process(samples, probability)
        if not was_in_speech and self._segmenter.is_in_speech:
            with self._flow_lock:
                self.flow.speech_started(at=datetime.now())
        for segment in segments:
            self._queue(self._utterances, np.asarray(segment.samples, dtype=np.float32))

    def _queue(self, target: list[np.ndarray], samples: np.ndarray) -> None:
        with self._wake:
            target.append(samples)
            # Only the newest few matter; a backlog would answer things said long ago.
            del target[:-4]
            self._wake.notify_all()

    def _next(self, source: list[np.ndarray]) -> np.ndarray | None:
        with self._wake:
            while self._running.is_set() and not source:
                self._wake.wait(timeout=0.5)
            return source.pop(0) if source else None

    # MARK: - Utterances

    def _process_utterances(self) -> None:
        while self._running.is_set():
            samples = self._next(self._utterances)
            if samples is None or self._suspended:
                continue
            try:
                self._handle_utterance(samples)
            except Exception:
                log.exception("Could not handle what was heard")

    def _handle_utterance(self, samples: np.ndarray) -> None:
        if self._awaiting_answer.is_set():
            # A "yes" from the TV must not confirm anything.
            if not self._speaker_allows(samples):
                return
            heard = self.recognizer.transcribe(samples)
            self._event("heard", heard)
            self._resolve(confirmation_parser.parse(heard, language=self.language))
            return
        with self._flow_lock:
            is_wake_check = isinstance(self.flow.phase, ListeningForWake)
        if not is_wake_check:
            self._set_status(Status.TRANSCRIBING)
        transcript = self._transcribe(samples, wake_check_only=is_wake_check)
        if transcript is None or self._suspended:
            return
        if self._needs_speaker_check(transcript, is_wake_check) and not self._speaker_allows(samples):
            self._event("ignored", transcript)
            if not is_wake_check:
                self._set_status(Status.AWAKE)
            return
        with self._flow_lock:
            action = self.flow.heard(transcript, at=datetime.now())
        if not isinstance(action, NoAction):
            self._event("heard", transcript)
        self._perform(action)
        if not is_wake_check and isinstance(action, NoAction):
            self._set_status(Status.AWAKE)

    def _transcribe(self, samples: np.ndarray, wake_check_only: bool) -> str | None:
        """While waiting for the wake word only the opening seconds are transcribed; the rest only if it is there."""
        if not wake_check_only:
            return self.recognizer.transcribe(samples)
        probe = self.wake_recognizer.transcribe(samples[: int(WAKE_PROBE_SECONDS * SAMPLE_RATE)])
        log.debug("Wake probe (%.1f s): %r", len(samples) / SAMPLE_RATE, probe)
        match = self.matcher.match(probe)
        if match is None:
            return None
        # A bare "Bilge" needs nothing more; anything after it is transcribed again with the full model.
        if not match.command and len(samples) <= WAKE_PROBE_SECONDS * SAMPLE_RATE:
            return probe
        return self._with_wake_word(self.recognizer.transcribe(samples))

    def _with_wake_word(self, transcript: str) -> str:
        """The quick model has already heard the wake word. The full model, listening in English, often spells
        the Turkish name differently ("Bilgé", "Bilgi"), which would make the flow drop the command."""
        if self.matcher.match(transcript) is not None:
            return transcript
        words = transcript.split()
        if words and similarity(folded(words[0]), folded(self.options.wake_phrase)) >= WAKE_SPELLING_SIMILARITY:
            words = words[1:]
        return f"{self.options.wake_phrase}, {' '.join(words)}".strip(", ")

    def _needs_speaker_check(self, transcript: str, is_wake_check: bool) -> bool:
        """A bare wake word is too short to judge; the command after it is checked instead."""
        if not self.speaker_gate or not self.speaker_gate.is_active:
            return False
        if not is_wake_check:
            return True
        match = self.matcher.match(transcript)
        return match is not None and bool(match.command)

    def _speaker_allows(self, samples: np.ndarray) -> bool:
        if not self.speaker_gate or not self.speaker_gate.is_active:
            return True
        return self.speaker_gate.check(samples) is not Decision.REJECTED

    def _tick(self) -> None:
        while not self._stopping.wait(TICK_SECONDS):
            with self._flow_lock:
                action = self.flow.tick(at=datetime.now())
            self._perform(action)

    # MARK: - Turns

    def _perform(self, action) -> None:
        if isinstance(action, AcknowledgeWake):
            self.speech.play(tone(self.speech.device.sample_rate, (880, 1320)))
            self._set_status(Status.AWAKE)
        elif isinstance(action, RunCommand | RunWorkInput):
            text = action.command if isinstance(action, RunCommand) else action.text
            self._turn = threading.Thread(target=self._run_turn, args=(text,), name="bilge-turn", daemon=True)
            self._turn.start()
        elif isinstance(action, ReturnToIdle):
            if action.timed_out:
                self.speech.play(tone(self.speech.device.sample_rate, (660, 440)))
            self.agent.forget_conversation()
            self._set_status(Status.LISTENING)

    def _run_turn(self, command: str) -> None:
        self._suspend()
        self._set_status(Status.THINKING)
        with self._flow_lock:
            self.flow.response_started()
        try:
            self._thinking = True
            try:
                reply = self.agent.handle(command).text
            finally:
                self._thinking = False
            # Stopped or redirected while it was still thinking: the answer is no longer wanted.
            if not self._stopped_by_user and self._barge_command is None:
                self._say(reply)
        except Exception as error:
            log.exception("The turn failed")
            self._event("error", str(error))
            self.speech.play(tone(self.speech.device.sample_rate, (440, 330, 220)))
        self._settle_barge_in()
        self._resume()
        allow_follow_up = self._barge_command is not None or (not self._stopped_by_user and self.options.follow_up)
        self._stopped_by_user = False
        with self._flow_lock:
            self.flow.response_finished(at=datetime.now(), allow_follow_up=allow_follow_up)
            awaiting = self.flow.is_awaiting_speech
        if not awaiting:
            self.agent.forget_conversation()
        self._set_status(Status.AWAKE if awaiting else Status.LISTENING)
        if self._barge_command is not None:
            command, self._barge_command = self._barge_command, None
            with self._flow_lock:
                action = self.flow.heard(command, at=datetime.now())
            self._perform(action)

    def _say(self, text: str) -> None:
        if not text.strip():
            return
        self._reply_so_far = ""
        self._event("reply", text)
        self._speaking = True
        self._set_status(Status.SPEAKING)

        def spoken(sentence: str) -> None:
            self._reply_so_far = f"{self._reply_so_far} {sentence}".strip()

        try:
            self.speech.speak(text, on_sentence=spoken)
        finally:
            self._speaking = False

    def _suspend(self) -> None:
        self._suspended = True
        self._segmenter.reset()
        self._barge_segmenter.reset()

    def _resume(self) -> None:
        self._vad.reset()
        self._segmenter.reset()
        self._suspended = False

    # MARK: - Cutting in

    def _process_barge_ins(self) -> None:
        while self._running.is_set():
            samples = self._next(self._barge_utterances)
            if samples is None or not (self._speaking or self._thinking):
                continue
            try:
                self._evaluate_barge_in(samples)
            except Exception:
                log.exception("Could not check a cut-in")

    def _evaluate_barge_in(self, samples: np.ndarray) -> None:
        quick = self.wake_recognizer.transcribe(samples)
        log.debug("Cut-in probe (%.1f s): %r", len(samples) / SAMPLE_RATE, quick)
        if self._asking:
            # Over a confirmation question no wake word is needed, so every utterance is read properly.
            heard = self.recognizer.transcribe(samples)
        elif not self._sounds_like_wake_word(quick):
            return
        else:
            # The quick model only spots that the user is talking to Bilge; the full one decides what they said
            # ("Bilge dur" came out of the quick one as "Bilge tur", a request).
            heard = self._with_wake_word(self.recognizer.transcribe(samples))
        if self._asking and confirmation_parser.parse(heard, language=self.language) is Answer.REJECTED:
            # "Hayır" over the confirmation question is the answer; there is no need to wait for it to end.
            self._stopped_by_user = True
            self._last_heard = heard
            self._event("cut-in", heard)
            self.speech.stop()
            return
        decision = self._barge_detector.evaluate(heard, speaking=self._reply_so_far)
        if isinstance(decision, Command):
            self._barge_command = decision.command
        elif isinstance(decision, Stop):
            self._stopped_by_user = True
        else:
            return
        self._last_heard = heard
        self._event("cut-in", heard)
        self.interrupt()

    def _sounds_like_wake_word(self, quick: str) -> bool:
        """A loose gate: over Bilge's own voice the quick model writes the name as "Bilgeye" or "Bilgetler"."""
        if self.matcher.match(quick) is not None:
            return True
        wake = folded(self.options.wake_phrase)
        return any(similarity(word, wake) >= CUT_IN_GATE_SIMILARITY for word in folded(quick).split()[:2])

    def _settle_barge_in(self) -> None:
        """What the user started saying near the end of the reply is still judged, not thrown away."""
        pending = self._barge_segmenter.flush()
        self._barge_segmenter.reset()
        if pending is not None and self.options.barge_in and len(pending.samples) > CHUNK:
            self._speaking = True
            try:
                self._evaluate_barge_in(np.asarray(pending.samples, dtype=np.float32))
            finally:
                self._speaking = False

    # MARK: - Confirmation

    def confirm(self, question: str) -> bool:
        """Asks out loud and waits for a spoken yes or no (no wake word needed). Called on the turn thread."""
        self._stopped_by_user = False
        self._asking = True
        try:
            self._say(question)
            self._settle_barge_in()
        finally:
            self._asking = False
        # A "no" said over the question is the answer; an early "yes" is not taken, agreeing by mistake costs more.
        if (
            self._stopped_by_user
            and confirmation_parser.parse(self._last_heard, language=self.language) is Answer.REJECTED
        ):
            self._stopped_by_user = False
            return False
        self._stopped_by_user = False
        self._pending_answer = None
        self._answered.clear()
        self._awaiting_answer.set()
        self._resume()
        self._set_status(Status.CONFIRMING)
        answered = self._answered.wait(CONFIRMATION_TIMEOUT)
        if not answered and self._segmenter.is_in_speech:
            answered = self._answered.wait(CONFIRMATION_GRACE)
        self._awaiting_answer.clear()
        self._suspend()
        self._set_status(Status.THINKING)
        answer = self._pending_answer if answered else Answer.UNCLEAR
        self._event("answer", str(answer))
        return answer is Answer.CONFIRMED

    def _resolve(self, answer: Answer) -> None:
        if self._awaiting_answer.is_set():
            self._pending_answer = answer
            self._answered.set()

    # MARK: - Events

    def _set_status(self, status: Status) -> None:
        if status is not self.status:
            self.status = status
            self._event("status", status.value)

    def _event(self, kind: str, text: str) -> None:
        try:
            self._on_event(kind, text)
        except Exception:
            log.exception("Event handler failed")
