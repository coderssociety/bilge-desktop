"""`bilge` on the command line: listen by voice, chat by typing, and manage settings, keys and models."""

import argparse
import getpass
import sys
import threading
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from keyring.errors import KeyringError

from bilge import assembly, calendars, config
from bilge.core.language import AssistantLanguage
from bilge.llm.providers import PRESETS, ProviderError, make_provider
from bilge.models.downloader import DownloadError


def ask_yes_no(question: str) -> bool:
    answer = input(f"  ? {question} [e/h] ").strip().lower()
    return answer in {"e", "evet", "y", "yes"}


def _settings(args: argparse.Namespace) -> config.Settings:
    settings = config.load_settings()
    if getattr(args, "language", None):
        settings.language = args.language
    return settings


def chat(args: argparse.Namespace) -> int:
    settings = _settings(args)
    agent = assembly.build_agent(
        settings,
        confirm=ask_yes_no,
        provider=args.provider,
        model=args.model,
        announce=lambda text: print(f"\n« {text}"),
    )
    turkish = settings.assistant_language is AssistantLanguage.TURKISH
    print("Bilge (çıkmak için Ctrl+D)" if turkish else "Bilge (Ctrl+D to quit)")
    while True:
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not command:
            continue
        try:
            # In a hands-free mode (dictation, spreadsheet editing) a line is that mode's input.
            outcome = agent.handle_work_input(command) if agent.work_session else agent.handle(command)
            if outcome.text:
                print(outcome.text)
        except ProviderError as error:
            print(f"! {error}", file=sys.stderr)


def listen(args: argparse.Namespace) -> int:
    settings = _settings(args)
    _download(settings)

    def on_event(kind: str, text: str) -> None:
        labels = {"heard": "»", "reply": "«", "cut-in": "✋", "answer": "?", "error": "!", "ignored": "–"}
        if kind == "status":
            print(f"  [{text}]", flush=True)
        elif kind in labels:
            print(f"{labels[kind]} {text}", flush=True)

    assistant, front_end = assembly.build_voice_assistant(settings, on_event, provider=args.provider, model=args.model)
    assistant.start()
    front_end.start()
    turkish = settings.assistant_language is AssistantLanguage.TURKISH
    print("“Bilge” de; çıkmak için Ctrl+C." if turkish else "Say “Bilge”; Ctrl+C to quit.", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print()
    finally:
        front_end.stop()
        assistant.stop()
    return 0


def _download(settings: config.Settings) -> None:
    shown: dict[str, int] = {}

    def progress(spec, done: int, total: int) -> None:
        percent = done * 100 // max(total, 1)
        if shown.get(spec.name) != percent and percent % 5 == 0:
            shown[spec.name] = percent
            print(f"  {spec.name}: %{percent} ({total / 1e9:.2f} GB)", flush=True)

    assembly.download_missing(assembly.voice_models(settings), progress)


def download(args: argparse.Namespace) -> int:
    _download(_settings(args))
    print("Models are ready.")
    return 0


def say(args: argparse.Namespace) -> int:
    import time

    from bilge.voice import models
    from bilge.voice.audio_io import SoundDevice
    from bilge.voice.speech_output import SpeechOutput
    from bilge.voice.supertonic import Supertonic

    settings = _settings(args)
    assembly.download_missing((models.SUPERTONIC,))
    device = SoundDevice(settings.voice.input_device, settings.voice.output_device)
    output = SpeechOutput(Supertonic(assembly.models_dir() / models.SUPERTONIC.name), device,
                          settings.assistant_language, args.voice or settings.voice.voice)  # fmt: skip
    device.start(lambda microphone, played: None)
    try:
        output.speak(args.text)
        time.sleep(0.3)
    finally:
        device.stop()
    return 0


def devices(args: argparse.Namespace) -> int:
    import sounddevice as sd

    print(sd.query_devices())
    return 0


def enroll(args: argparse.Namespace) -> int:
    """Records five short sentences and stores the voice's embeddings (never the recordings)."""
    import numpy as np
    import sounddevice as sd
    import soxr

    from bilge.voice import models
    from bilge.voice.speaker import CampPlus, EnrollmentError, VoiceStore

    settings = _settings(args)
    assembly.download_missing((models.CAMPLUS,))
    model = CampPlus(assembly.models_dir() / models.CAMPLUS.name / models.CAMPLUS_FILE)
    turkish = settings.assistant_language is AssistantLanguage.TURKISH
    sentences = ENROLL_TR if turkish else ENROLL_EN
    rate = int(sd.query_devices(settings.voice.input_device, "input")["default_samplerate"])
    embeddings = []
    for sentence in sentences:
        input(f"\n{'Enter’a bas, sonra oku' if turkish else 'Press Enter, then read'}: “{sentence}”")
        audio = sd.rec(int(ENROLL_SECONDS * rate), samplerate=rate, channels=1, dtype="float32",
                       device=settings.voice.input_device)  # fmt: skip
        sd.wait()
        embeddings.append(model.embedding(soxr.resample(audio[:, 0], rate, 16_000).astype(np.float32)))
    try:
        stored = VoiceStore(config.data_dir() / "voiceprint.json").enroll(embeddings)
    except EnrollmentError as error:
        print(f"! {error}", file=sys.stderr)
        return 1
    settings.voice.speaker_check = True
    config.save_settings(settings)
    print(f"{'Sesin kaydedildi' if turkish else 'Your voice is saved'} (threshold {stored.threshold:.2f}).")
    return 0


ENROLL_SECONDS = 3.5
ENROLL_TR = [
    "Bilge, yarın sabah saat yedide beni uyandır.",
    "Bugün hava nasıl olacak, yağmur yağacak mı?",
    "Ahmet'e akşam yemeğe geç kalacağımı yaz.",
    "Bu hafta takvimimde hangi toplantılar var?",
    "Sesi biraz kıs ve sakin bir şarkı aç.",
]
ENROLL_EN = [
    "Bilge, wake me up tomorrow at seven.",
    "What will the weather be like today, will it rain?",
    "Tell Ahmet I'll be late for dinner tonight.",
    "Which meetings are on my calendar this week?",
    "Turn the volume down a little and play something calm.",
]


def models_list(args: argparse.Namespace) -> int:
    settings = config.load_settings()
    preset = args.provider or settings.model.provider
    provider = make_provider(
        preset, "-", config.api_key(preset), settings.model.base_url if not args.provider else None
    )
    for model in provider.list_models():
        print(model)
    return 0


def use(args: argparse.Namespace) -> int:
    if args.provider not in PRESETS:
        print(f"Unknown provider. Choose one of: {', '.join(PRESETS)}", file=sys.stderr)
        return 2
    settings = config.load_settings()
    settings.model = config.ModelSettings(args.provider, args.model, args.base_url)
    config.save_settings(settings)
    print(f"{PRESETS[args.provider].name}: {args.model}")
    return 0


def key(args: argparse.Namespace) -> int:
    if args.provider not in PRESETS:
        print(f"Unknown provider. Choose one of: {', '.join(PRESETS)}", file=sys.stderr)
        return 2
    if args.delete:
        config.delete_api_key(args.provider)
        return 0
    secret = getpass.getpass(f"{PRESETS[args.provider].name} API key: ").strip()
    if not secret:
        return 1
    try:
        config.store_api_key(args.provider, secret)
    except KeyringError as error:
        print(f"Could not store the key in the system key store: {error}", file=sys.stderr)
        return 1
    print("Saved in the system key store.")
    return 0


def calendar(args: argparse.Namespace) -> int:
    """Connects a calendar. Passwords and the secret iCal address are typed hidden and kept in the key store, and
    only once the calendar has answered, so a typo doesn't replace a working setup."""
    settings = config.load_settings()
    if args.kind == "off":
        settings.calendar = config.CalendarSettings()
        config.save_settings(settings)
        for secret_name in (assembly.CALDAV_SECRET, assembly.ICS_SECRET):
            config.delete_api_key(secret_name)
        print("Calendar disconnected.")
        return 0
    if args.kind == "caldav":
        if not args.url:
            print("A CalDAV address is needed: bilge calendar caldav <address> --user <name>", file=sys.stderr)
            return 2
        if not calendars.is_secure_address(args.url) or "@" in (urlsplit(args.url).netloc or ""):
            print("The address must start with https:// and hold no user name or password.", file=sys.stderr)
            return 2
        secret_name = assembly.CALDAV_SECRET
        secret = getpass.getpass("CalDAV password (an app password where the service offers one): ")
        chosen = config.CalendarSettings("caldav", args.url, args.user or "", args.name or "")
        source: calendars.CalendarSource = calendars.CalDAVSource(chosen.url, chosen.username, secret, chosen.name)
    else:
        secret_name = assembly.ICS_SECRET
        secret = getpass.getpass("Secret iCal address (it is kept in the key store, not shown): ").strip()
        if not secret.lower().startswith("https://"):
            print("The address must start with https://", file=sys.stderr)
            return 2
        chosen = config.CalendarSettings("ics")
        source = calendars.ICSSource(secret)
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        events = source.events(start, start + timedelta(days=7))
    except calendars.CalendarError as error:
        print(f"! The calendar didn't answer: {error}", file=sys.stderr)
        return 1
    try:
        config.store_api_key(secret_name, secret)
    except KeyringError as error:
        print(f"Could not store it in the system key store: {error}", file=sys.stderr)
        return 1
    settings.calendar = chosen
    config.save_settings(settings)
    print(f"Connected. {len(events)} events in the next 7 days.")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="bilge")
    commands = root.add_subparsers(dest="command", required=True)
    languages = [lang.value for lang in AssistantLanguage]

    for name, run, help_text in [
        ("listen", listen, "talk to Bilge by voice"),
        ("chat", chat, "talk to Bilge by typing"),
    ]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--provider", choices=sorted(PRESETS))
        command.add_argument("--model")
        command.add_argument("--language", choices=languages)
        command.set_defaults(run=run)

    download_command = commands.add_parser("download", help="download the voice models")
    download_command.add_argument("--language", choices=languages)
    download_command.set_defaults(run=download)

    say_command = commands.add_parser("say", help="speak a sentence with Bilge's voice")
    say_command.add_argument("text")
    say_command.add_argument("--voice")
    say_command.add_argument("--language", choices=languages)
    say_command.set_defaults(run=say)

    commands.add_parser("devices", help="list microphones and speakers").set_defaults(run=devices)

    enroll_command = commands.add_parser("enroll", help="teach Bilge your voice")
    enroll_command.add_argument("--language", choices=languages)
    enroll_command.set_defaults(run=enroll)

    models_command = commands.add_parser("models", help="list a provider's language models")
    models_command.add_argument("--provider", choices=sorted(PRESETS))
    models_command.set_defaults(run=models_list)

    use_command = commands.add_parser("use", help="choose the provider and model")
    use_command.add_argument("provider")
    use_command.add_argument("model")
    use_command.add_argument("--base-url")
    use_command.set_defaults(run=use)

    calendar_command = commands.add_parser("calendar", help="connect a CalDAV calendar or a read-only iCal address")
    calendar_command.add_argument("kind", choices=["caldav", "ics", "off"])
    calendar_command.add_argument("url", nargs="?", help="the CalDAV server or calendar address")
    calendar_command.add_argument("--user")
    calendar_command.add_argument("--name", help="the calendar new events go to")
    calendar_command.set_defaults(run=calendar)

    key_command = commands.add_parser("key", help="store or delete a provider's API key")
    key_command.add_argument("provider")
    key_command.add_argument("--delete", action="store_true")
    key_command.set_defaults(run=key)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.run(args)
    except (ProviderError, DownloadError, RuntimeError) as error:
        print(f"! {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
