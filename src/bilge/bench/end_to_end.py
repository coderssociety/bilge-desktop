"""End-to-end check of the voice loop without a person: a script is spoken (in another Supertonic voice) into a
simulated microphone that also hears Bilge's replies as room echo, and each line is checked for whether Bilge
answered, stayed quiet or stopped talking as expected.

    uv run python -m bilge.bench.end_to_end --models <models dir> --provider lmstudio --model <id> [--language en]
"""

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soxr

from bilge.brain.agent import Agent
from bilge.core.language import AssistantLanguage
from bilge.llm.providers import make_provider
from bilge.models.downloader import Downloader
from bilge.tools.base import Registry
from bilge.tools.builtin import internet
from bilge.tools.builtin.calculator import calculator
from bilge.tools.builtin.clock import current_date_time
from bilge.tools.builtin.memory import memory_tools
from bilge.tools.memory_store import MemoryStore
from bilge.voice.assistant import Status, VoiceAssistant
from bilge.voice.audio_io import FrontEnd, SimulatedDevice
from bilge.voice.echo import EchoCanceller
from bilge.voice.models import SUPERTONIC, WHISPER_BASE, WHISPER_TURBO
from bilge.voice.recognizers import WhisperRecognizer
from bilge.voice.speech_output import SpeechOutput
from bilge.voice.supertonic import Supertonic


@dataclass(frozen=True)
class Line:
    pause_before: float
    text: str
    expects_reply: bool
    interrupts: bool = False

    @property
    def waits_for_speech(self) -> bool:
        """Cut-ins are said a moment after Bilge starts talking; everything else once it has finished."""
        return self.interrupts


TURKISH = [
    Line(1.5, "Bugün hava çok güzel, dışarı çıkalım.", False),
    Line(2.0, "Bilge, saat kaç?", True),
    Line(2.0, "Bilge.", False),
    Line(1.0, "Dolar kaç lira?", True),
    Line(2.0, "Bilge, yüz yirmi beşin yüzde on sekizi kaç eder?", True),
    Line(1.0, "Teşekkür ederim.", True),
    Line(7.0, "Bilge, hafızanı tamamen temizle.", True),
    Line(0.5, "Hayır.", True),
    Line(7.0, "Bilge, bana İstanbul'un tarihini anlat.", True),
    Line(2.0, "Bilge, dur.", False, interrupts=True),
    Line(7.0, "Bilge, bana Ankara'yı anlat.", True),
    Line(2.0, "Bilge, saat kaç?", True, interrupts=True),
]
ENGLISH = [
    Line(1.5, "The weather is lovely today, let's go out.", False),
    Line(2.0, "Bilge, what time is it?", True),
    Line(2.0, "Bilge.", False),
    Line(1.0, "How much is the dollar in euros?", True),
    Line(2.0, "Bilge, what is 18 percent of 125?", True),
    Line(1.0, "Thank you.", True),
    Line(7.0, "Bilge, clear your whole memory.", True),
    Line(0.5, "No.", True),
    Line(7.0, "Bilge, tell me about the history of London.", True),
    Line(2.0, "Bilge, stop.", False, interrupts=True),
    Line(7.0, "Bilge, tell me about New York.", True),
    Line(2.0, "Bilge, what time is it?", True, interrupts=True),
]
USER_VOICE = "M2"
BILGE_VOICE = "F1"


IDLE = (Status.LISTENING, Status.AWAKE, Status.CONFIRMING)
WAIT_LIMIT = 60.0
# Quiet time after which a line counts as dealt with: Bilge needs a moment to notice it was spoken to at all.
SETTLED_SECONDS = 2.5


def wait_until_settled(
    assistant: VoiceAssistant, events: list, since: float, expects_reply: bool, start: float
) -> None:
    """Waits for Bilge to react to a line (a reply when one is expected), then for things to go quiet."""
    deadline = time.monotonic() + WAIT_LIMIT
    while time.monotonic() < deadline:
        now = time.monotonic() - start
        replied = any(t >= since and kind == "reply" for t, kind, _ in events)
        last_event = max((t for t, _, _ in events), default=0.0)
        quiet = now - max(last_event, since) >= SETTLED_SECONDS
        if assistant.status in IDLE and quiet and (replied or not expects_reply):
            return
        time.sleep(0.05)


def spoken_line(tts: Supertonic, text: str, language: AssistantLanguage) -> np.ndarray:
    """In English the user still says "Bilge" the Turkish way, so that word is voiced in Turkish."""
    if language is AssistantLanguage.TURKISH or not text.startswith("Bilge"):
        return tts.synthesize(text, language, USER_VOICE, seed=1)
    name = _trimmed(tts.synthesize("Bilge.", AssistantLanguage.TURKISH, USER_VOICE, seed=1))
    rest = text[len("Bilge") :].lstrip(" ,.")
    if not rest:
        return name
    gap = np.zeros(int(0.12 * tts.sample_rate), dtype=np.float32)
    return np.concatenate([name, gap, _trimmed(tts.synthesize(rest, language, USER_VOICE, seed=1))])


def _trimmed(audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    loud = np.flatnonzero(np.abs(audio) > threshold)
    return audio[loud[0] : loud[-1] + 1] if len(loud) else audio


def wait_until_speaking(assistant: VoiceAssistant) -> None:
    deadline = time.monotonic() + WAIT_LIMIT
    while time.monotonic() < deadline and assistant.status is not Status.SPEAKING:
        time.sleep(0.05)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--provider", default="lmstudio")
    parser.add_argument("--model", required=True)
    parser.add_argument("--language", choices=["tr", "en"], default="tr")
    parser.add_argument("--debug", action="store_true", help="log what the recognizers heard")
    args = parser.parse_args(argv)
    if args.debug:
        import logging

        logging.basicConfig(level=logging.WARNING, format="  %(relativeCreated)7.0fms %(message)s")
        logging.getLogger("bilge.voice.assistant").setLevel(logging.DEBUG)
    language = AssistantLanguage(args.language)
    script = ENGLISH if language is AssistantLanguage.ENGLISH else TURKISH

    tts = Supertonic(args.models / SUPERTONIC.name)
    device = SimulatedDevice()
    events: list[tuple[float, str, str]] = []
    start = time.monotonic()

    def on_event(kind: str, text: str) -> None:
        events.append((time.monotonic() - start, kind, text))
        print(f"  {time.monotonic() - start:6.1f}s {kind}: {text}", flush=True)

    memory = MemoryStore(args.models / "bench-memory.json")
    memory.forget_all()
    memory.remember("kahvemi şekersiz içerim" if language is AssistantLanguage.TURKISH else "I take my coffee black")
    registry = Registry([current_date_time(language), calculator(language), internet.weather(language, lambda: "İstanbul"),
                         internet.exchange_rate(language), internet.news(language)])  # fmt: skip
    holder: dict[str, VoiceAssistant] = {}
    agent = Agent(make_provider(args.provider, args.model), registry, confirm=lambda q: holder["a"].confirm(q),
                  language=language, memory=memory.prompt_lines)  # fmt: skip
    for tool in memory_tools(memory, language, lambda: agent.last_reply):
        registry.add(tool)
    downloader = Downloader(args.models)
    for spec in (SUPERTONIC, WHISPER_TURBO, WHISPER_BASE):
        downloader.download(spec) if not downloader.is_downloaded(spec) else None
    recognizer = WhisperRecognizer(str(args.models / WHISPER_TURBO.name), language, hint="Bilge")
    wake = WhisperRecognizer(str(args.models / WHISPER_BASE.name), AssistantLanguage.TURKISH, hint="Bilge")
    speech = SpeechOutput(tts, device, language, BILGE_VOICE)
    assistant = VoiceAssistant(recognizer, speech, agent, language, on_event=on_event, wake_recognizer=wake)
    holder["a"] = assistant
    front = FrontEnd(device, assistant.on_chunk, EchoCanceller())
    assistant.start()
    front.start()

    marks: list[float] = []
    for i, line in enumerate(script):
        if line.waits_for_speech:
            wait_until_speaking(assistant)
        elif i:
            wait_until_settled(assistant, events, marks[-1], script[i - 1].expects_reply, start)
        time.sleep(line.pause_before)
        audio = spoken_line(tts, line.text, language)
        marks.append(time.monotonic() - start)
        print(f"> {marks[-1]:6.1f}s user: {line.text}", flush=True)
        device.say(soxr.resample(audio, tts.sample_rate, device.sample_rate).astype(np.float32))
        while not device.script_done:
            time.sleep(0.05)
    wait_until_settled(assistant, events, marks[-1], script[-1].expects_reply, start)
    front.stop()
    assistant.stop()

    passed = 0
    for i, line in enumerate(script):
        begin = marks[i]
        end = marks[i + 1] if i + 1 < len(marks) else float("inf")
        window = [(t, kind) for t, kind, _ in events if begin <= t < end]
        replied = any(kind == "reply" for _, kind in window)
        cut_in = any(kind == "cut-in" for _, kind in window)
        ok = replied == line.expects_reply and (cut_in if line.interrupts else True)
        passed += ok
        print(
            f"{'✓' if ok else '✗'} {line.text}  (reply={replied}{', cut-in=' + str(cut_in) if line.interrupts else ''})"
        )
    print(f"{passed}/{len(script)}")
    return 0 if passed == len(script) else 1


if __name__ == "__main__":
    sys.exit(main())
