"""Builds the assistant from the settings: the one place the CLI, the tray app and the benchmarks share."""

from collections.abc import Callable
from pathlib import Path

from bilge import config
from bilge.brain.action_log import ActionLog
from bilge.brain.agent import Agent, Confirmer
from bilge.core.language import AssistantLanguage
from bilge.llm.providers import ProviderError, make_provider
from bilge.models.downloader import Downloader, ModelSpec
from bilge.tools.base import Registry
from bilge.tools.builtin import internet
from bilge.tools.builtin.calculator import calculator
from bilge.tools.builtin.clock import current_date_time
from bilge.tools.builtin.memory import memory_tools
from bilge.tools.memory_store import MemoryStore


def models_dir() -> Path:
    return config.data_dir() / "models"


def build_agent(
    settings: config.Settings, confirm: Confirmer, provider: str | None = None, model: str | None = None
) -> Agent:
    language = settings.assistant_language
    preset = provider or settings.model.provider
    chosen = model or settings.model.model
    if not chosen:
        raise ProviderError("No model chosen. Run `bilge models` to list them, then `bilge use <provider> <model>`.")
    chat = make_provider(preset, chosen, config.api_key(preset), settings.model.base_url if not provider else None)
    memory = MemoryStore(config.data_dir() / "memory.json")
    registry = Registry([
        current_date_time(language),
        calculator(language),
        internet.weather(language, lambda: settings.weather_city),
        internet.exchange_rate(language),
        internet.news(language),
        internet.read_web_page(language),
    ])  # fmt: skip
    agent = Agent(chat, registry, confirm=confirm, language=language, memory=memory.prompt_lines,
                  action_log=ActionLog(config.data_dir() / "actions.jsonl"))  # fmt: skip
    for tool in memory_tools(memory, language, lambda: agent.last_reply):
        registry.add(tool)
    return agent


def voice_models(settings: config.Settings) -> tuple[ModelSpec, ...]:
    from bilge.voice import models

    needed = [models.SUPERTONIC, models.WHISPER_BASE]
    if settings.voice.recognizer == "local":
        needed.append(models.WHISPER_TURBO)
    if settings.voice.speaker_check:
        needed.append(models.CAMPLUS)
    return tuple(needed)


def download_missing(
    specs: tuple[ModelSpec, ...], progress: Callable[[ModelSpec, int, int], None] | None = None
) -> None:
    downloader = Downloader(models_dir())
    for spec in specs:
        if not downloader.is_downloaded(spec):
            downloader.download(
                spec, progress=(lambda done, total, s=spec: progress(s, done, total)) if progress else None
            )


def build_voice_assistant(settings: config.Settings, on_event, provider: str | None = None, model: str | None = None):
    """Returns (assistant, front_end); call front_end.start() and assistant.start() to begin listening."""
    from bilge.voice import models
    from bilge.voice.assistant import Options, VoiceAssistant
    from bilge.voice.audio_io import FrontEnd, SoundDevice
    from bilge.voice.echo import EchoCanceller
    from bilge.voice.recognizers import TRANSCRIPTION_PRESETS, APIRecognizer, WhisperRecognizer
    from bilge.voice.speaker import CampPlus, SpeakerGate, VoiceStore
    from bilge.voice.speech_output import SpeechOutput
    from bilge.voice.supertonic import Supertonic

    language = settings.assistant_language
    voice = settings.voice
    root = models_dir()
    if voice.recognizer == "local":
        recognizer = WhisperRecognizer(str(root / models.WHISPER_TURBO.name), language, hint="Bilge")
    elif voice.recognizer in TRANSCRIPTION_PRESETS:
        base_url, default_model = TRANSCRIPTION_PRESETS[voice.recognizer]
        key = config.api_key(voice.recognizer)
        if not key:
            raise ProviderError(f"Speech recognition through {voice.recognizer} needs an API key.")
        recognizer = APIRecognizer(base_url, key, voice.recognizer_model or default_model, language)
    else:
        raise ProviderError(f"Unknown speech recognizer: {voice.recognizer}")
    # The wake word is Turkish in both languages.
    wake = WhisperRecognizer(str(root / models.WHISPER_BASE.name), AssistantLanguage.TURKISH, hint="Bilge")
    device = SoundDevice(voice.input_device, voice.output_device)
    speech = SpeechOutput(Supertonic(root / models.SUPERTONIC.name), device, language, voice.voice)
    gate = None
    if voice.speaker_check:
        gate = SpeakerGate(VoiceStore(config.data_dir() / "voiceprint.json"),
                           CampPlus(root / models.CAMPLUS.name / models.CAMPLUS_FILE), enabled=True)  # fmt: skip
    holder: dict = {}
    agent = build_agent(
        settings, confirm=lambda question: holder["assistant"].confirm(question), provider=provider, model=model
    )
    options = Options(wake_phrase=voice.wake_phrase, follow_up=voice.follow_up, barge_in=voice.barge_in)
    assistant = VoiceAssistant(recognizer, speech, agent, language, options, gate, on_event, wake_recognizer=wake)
    holder["assistant"] = assistant
    front_end = FrontEnd(device, assistant.on_chunk, EchoCanceller() if voice.barge_in else None)
    return assistant, front_end
