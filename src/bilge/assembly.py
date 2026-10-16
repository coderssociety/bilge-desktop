"""Builds the assistant from the settings: the one place the CLI, the tray app and the benchmarks share."""

import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from bilge import calendars, config, desktop
from bilge.brain.action_log import ActionLog
from bilge.brain.agent import Agent, Confirmer
from bilge.brain.routing import Mode, Rule, rule
from bilge.core.dictation import dictation_command
from bilge.core.language import AssistantLanguage
from bilge.desktop.base import Desktop
from bilge.llm.providers import ProviderError, make_provider
from bilge.models.downloader import Downloader, ModelSpec
from bilge.tools.base import Registry, Tool
from bilge.tools.builtin import internet
from bilge.tools.builtin.briefing import Briefing, briefing_tool
from bilge.tools.builtin.calculator import calculator
from bilge.tools.builtin.calendar import calendar_tools
from bilge.tools.builtin.clock import current_date_time
from bilge.tools.builtin.memory import memory_tools
from bilge.tools.memory_store import MemoryStore

log = logging.getLogger(__name__)
CALDAV_SECRET = "caldav"
ICS_SECRET = "calendar-ics"


def models_dir() -> Path:
    return config.data_dir() / "models"


def calendar_source(settings: config.CalendarSettings) -> calendars.CalendarSource | None:
    if settings.kind == "caldav" and settings.url:
        return calendars.CalDAVSource(
            settings.url, settings.username, config.api_key(CALDAV_SECRET) or "", settings.name
        )
    if settings.kind == "outlook" and sys.platform == "win32":
        from bilge.desktop.windows.office import Outlook, OutlookCalendar

        return OutlookCalendar(Outlook())
    if settings.kind == "ics":
        url = config.api_key(ICS_SECRET)
        return calendars.ICSSource(url) if url else None
    return None


def build_agent(
    settings: config.Settings,
    confirm: Confirmer,
    provider: str | None = None,
    model: str | None = None,
    announce: Callable[[str], None] | None = None,
) -> Agent:
    """`announce` says something unprompted (a timer going off)."""
    language = settings.assistant_language
    preset = provider or settings.model.provider
    chosen = model or settings.model.model
    if not chosen:
        raise ProviderError("No model chosen. Run `bilge models` to list them, then `bilge use <provider> <model>`.")
    chat = make_provider(preset, chosen, config.api_key(preset), settings.model.base_url if not provider else None)
    memory = MemoryStore(config.data_dir() / "memory.json")
    weather = internet.weather(language, lambda: settings.weather_city)

    def calendar() -> calendars.CalendarSource | None:
        return calendar_source(settings.calendar)

    briefing = Briefing(language, weather, calendar, settings.voice.wake_phrase)
    news_reading = internet.NewsReading()
    registry = Registry([
        current_date_time(language),
        calculator(language),
        weather,
        internet.exchange_rate(language),
        internet.news(language, news_reading),
        internet.read_web_page(language),
        briefing_tool(briefing),
        *calendar_tools(calendar, language),
    ])  # fmt: skip
    rules: list[Rule] = [rule("dailyBriefing", briefing.claims)]
    modes: list[Mode] = []
    found = desktop.current(language)
    registry.add(internet.news_article(language, news_reading, found.opener.open if found is not None else None))
    # Tools that refer to "the previous answer" are built before the agent that remembers it.
    built: list[Agent] = []
    if found is not None:
        last_reply = lambda: built[0].last_reply if built else None  # noqa: E731
        tools, desktop_rules, desktop_modes = _desktop_tools(found, language, announce, last_reply)
        for tool in tools:
            registry.add(tool)
        rules = [*desktop_rules, *rules]
        modes = desktop_modes
    agent = Agent(chat, registry, confirm=confirm, language=language, memory=memory.prompt_lines,
                  action_log=ActionLog(config.data_dir() / "actions.jsonl"), rules=rules, modes=modes)  # fmt: skip
    built.append(agent)
    for tool in memory_tools(memory, language, lambda: agent.last_reply):
        registry.add(tool)
    return agent


def _desktop_tools(
    found: Desktop,
    language: AssistantLanguage,
    announce: Callable[[str], None] | None,
    last_reply: Callable[[], str | None],
) -> tuple[list[Tool], list[Rule], list[Mode]]:
    from bilge.desktop.calc import LibreOfficeCalc
    from bilge.desktop.process import Runner
    from bilge.tools.desktop import apps, clipboard, files, sound, spreadsheet, system, timers, typing, web

    def alert(message: str) -> None:
        try:
            found.notifier.notify("Bilge", message)
        except Exception:  # noqa: BLE001 - a missing notification must not silence the spoken one
            log.info("Could not show a notification", exc_info=True)
        if announce is not None:
            announce(message)

    dictation = typing.DictationSession(found.keyboard, language)
    sheet = spreadsheet.SpreadsheetSession(language)
    sheet_tool = spreadsheet.SpreadsheetTool(_spreadsheet_apps(LibreOfficeCalc(Runner())), sheet, language)
    tools = [
        *apps.app_tools(apps.AppCatalog(found.apps), language),
        sound.volume_tool(found.volume, language),
        sound.music_tool(found.media, language),
        *system.system_tools(found.session, found.network, found.settings, found.screenshots, found.folders, language),
        *clipboard.clipboard_tools(found.clipboard, language, last_reply),
        typing.type_text_tool(found.keyboard, language),
        typing.start_dictation_tool(dictation, language),
        *files.file_tools(found.folders, found.opener, language),
        *web.web_tools(found.opener, language),
        *timers.timer_tools(timers.TimerService(alert, language), language),
        spreadsheet.spreadsheet_tool(sheet_tool),
        *_office_tools(language),
    ]
    rules = [
        rule("startDictation", lambda command: dictation_command.is_start(command, language)),
        rule("spreadsheet", sheet.claims, lambda command: {"command": command}),
    ]
    modes = [
        Mode(lambda: dictation.active, dictation.window, lambda _: True, dictation.end, takes=dictation.handle,
             owns=typing.dictation_owns(dictation)),
        Mode(lambda: sheet.active, lambda: sheet.window, sheet.accepts, lambda: setattr(sheet, "active", False),
             tools=frozenset({"spreadsheet"})),
    ]  # fmt: skip
    return tools, rules, modes


def _spreadsheet_apps(calc):
    if sys.platform != "win32":
        return calc
    from bilge.desktop.windows.office import ExcelSheets, SpreadsheetApps

    return SpreadsheetApps({"excel": ExcelSheets(), "calc": calc})


def _office_tools(language: AssistantLanguage) -> list[Tool]:
    if sys.platform != "win32":
        return []
    from bilge.desktop.windows.office import Outlook
    from bilge.tools.desktop.mail import mail_tools

    return mail_tools(Outlook(), language)


def voice_models(settings: config.Settings) -> tuple[ModelSpec, ...]:
    from bilge.voice import models, placement

    needed = [models.SUPERTONIC, models.WHISPER_BASE]
    if settings.voice.recognizer == "local":
        on_vulkan = placement.choose(settings.voice.accelerator).where is placement.Where.VULKAN
        needed.append(models.WHISPER_TURBO_GGML if on_vulkan else models.WHISPER_TURBO)
    if settings.voice.speaker_check:
        needed.append(models.CAMPLUS)
    return tuple(needed)


# Setup and the starting assistant may both ask for the same models; one downloads while the other waits and then
# finds them in place, instead of both writing the same partial files.
_DOWNLOADING = threading.Lock()


def download_missing(
    specs: tuple[ModelSpec, ...],
    progress: Callable[[ModelSpec, int, int], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> None:
    with _DOWNLOADING:
        downloader = Downloader(models_dir())
        for spec in specs:
            if not downloader.is_downloaded(spec):
                downloader.download(
                    spec,
                    progress=(lambda done, total, s=spec: progress(s, done, total)) if progress else None,
                    cancelled=cancelled,
                )


def build_voice_assistant(settings: config.Settings, on_event, provider: str | None = None, model: str | None = None):
    """Returns (assistant, front_end); call front_end.start() and assistant.start() to begin listening."""
    from bilge.voice import models
    from bilge.voice.assistant import Options, VoiceAssistant
    from bilge.voice.audio_io import FrontEnd, SoundDevice
    from bilge.voice.echo import EchoCanceller
    from bilge.voice.recognizers import GuardedRecognizer, WhisperRecognizer
    from bilge.voice.speaker import CampPlus, SpeakerGate, VoiceStore
    from bilge.voice.speech_output import SpeechOutput
    from bilge.voice.supertonic import Supertonic

    language = settings.assistant_language
    voice = settings.voice
    root = models_dir()
    holder: dict = {}
    agent = build_agent(
        settings,
        confirm=lambda question: holder["assistant"].confirm(question),
        provider=provider,
        model=model,
        announce=lambda text: holder["assistant"].announce(text),
    )
    # The wake word is Turkish in both languages.
    wake = GuardedRecognizer(
        WhisperRecognizer(str(root / models.WHISPER_BASE.name), AssistantLanguage.TURKISH, hint="Bilge")
    )
    if voice.recognizer == "local" and voice.unload_minutes:
        from bilge.voice.idle import IdleUnloadingRecognizer

        recognizer = GuardedRecognizer(
            IdleUnloadingRecognizer(lambda: _recognizer(voice, language, root), voice.unload_minutes * 60)
        )
    else:
        recognizer = GuardedRecognizer(_recognizer(voice, language, root))
    try:
        device = SoundDevice(voice.input_device, voice.output_device)
        speech = SpeechOutput(Supertonic(root / models.SUPERTONIC.name), device, language, voice.voice)
        gate = None
        if voice.speaker_check:
            gate = SpeakerGate(VoiceStore(config.data_dir() / "voiceprint.json"),
                               CampPlus(root / models.CAMPLUS.name / models.CAMPLUS_FILE), enabled=True)  # fmt: skip
    except BaseException:
        recognizer.close()
        raise
    options = Options(wake_phrase=voice.wake_phrase, follow_up=voice.follow_up, barge_in=voice.barge_in,
                      wake_word=voice.wake_word or not voice.hotkey)  # fmt: skip
    assistant = VoiceAssistant(recognizer, speech, agent, language, options, gate, on_event, wake_recognizer=wake)
    holder["assistant"] = assistant
    front_end = FrontEnd(device, assistant.on_chunk, EchoCanceller() if voice.barge_in else None)
    return assistant, front_end


def _recognizer(voice: config.VoiceSettings, language: AssistantLanguage, root: Path):
    from bilge.voice import models, placement
    from bilge.voice.recognizers import TRANSCRIPTION_PRESETS, APIRecognizer, WhisperRecognizer
    from bilge.voice.whisper_cpp import WhisperServer, WhisperServerError, server_program

    if voice.recognizer in TRANSCRIPTION_PRESETS:
        base_url, default_model = TRANSCRIPTION_PRESETS[voice.recognizer]
        key = config.api_key(voice.recognizer)
        if not key:
            raise ProviderError(f"Speech recognition through {voice.recognizer} needs an API key.")
        return APIRecognizer(base_url, key, voice.recognizer_model or default_model, language)
    if voice.recognizer != "local":
        raise ProviderError(f"Unknown speech recognizer: {voice.recognizer}")
    chosen = placement.choose(voice.accelerator)
    program = server_program()
    if chosen.where is placement.Where.VULKAN and program is not None:
        model = root / models.WHISPER_TURBO_GGML.name / models.WHISPER_TURBO_GGML_FILE
        server = WhisperServer(program, model, language, chosen.gpu, hint="Bilge",
                               pid_file=config.data_dir() / "whisper-server.pid")  # fmt: skip
        try:
            server.start()
        except WhisperServerError as error:
            raise ProviderError(
                f"Whisper could not start on {chosen.description}: {error}. "
                "Choose the processor under Settings → Recognition."
            ) from error
        return server
    device = "cuda" if chosen.where is placement.Where.CUDA else "cpu"
    return WhisperRecognizer(str(root / models.WHISPER_TURBO.name), language, device=device, hint="Bilge")
