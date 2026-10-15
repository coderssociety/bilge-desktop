"""`bilge` on the command line: a text chat with the assistant and its settings, before there is a voice."""

import argparse
import getpass
import sys

from keyring.errors import KeyringError

from bilge import config
from bilge.brain.action_log import ActionLog
from bilge.brain.agent import Agent
from bilge.core.language import AssistantLanguage
from bilge.llm.providers import PRESETS, ChatProvider, ProviderError, make_provider
from bilge.tools.base import Registry
from bilge.tools.builtin import internet
from bilge.tools.builtin.calculator import calculator
from bilge.tools.builtin.clock import current_date_time
from bilge.tools.builtin.memory import memory_tools
from bilge.tools.memory_store import MemoryStore


def build_agent(settings: config.Settings, provider: ChatProvider, language: AssistantLanguage) -> Agent:
    memory = MemoryStore(config.data_dir() / "memory.json")
    registry = Registry(
        [
            current_date_time(language),
            calculator(language),
            internet.weather(language, lambda: settings.weather_city),
            internet.exchange_rate(language),
            internet.news(language),
            internet.read_web_page(language),
        ]
    )
    agent = Agent(
        provider,
        registry,
        confirm=ask_yes_no,
        language=language,
        memory=memory.prompt_lines,
        action_log=ActionLog(config.data_dir() / "actions.jsonl"),
    )
    for tool in memory_tools(memory, language, lambda: agent.last_reply):
        registry.add(tool)
    return agent


def provider_from(settings: config.Settings, provider: str | None, model: str | None) -> ChatProvider:
    preset = provider or settings.model.provider
    chosen = model or settings.model.model
    if not chosen:
        raise ProviderError("No model chosen. Run `bilge models` to list them, then `bilge use <provider> <model>`.")
    return make_provider(preset, chosen, config.api_key(preset), settings.model.base_url if not provider else None)


def ask_yes_no(question: str) -> bool:
    answer = input(f"  ? {question} [e/h] ").strip().lower()
    return answer in {"e", "evet", "y", "yes"}


def chat(args: argparse.Namespace) -> int:
    settings = config.load_settings()
    language = AssistantLanguage(args.language) if args.language else settings.assistant_language
    agent = build_agent(settings, provider_from(settings, args.provider, args.model), language)
    print("Bilge (çıkmak için Ctrl+D)" if language is AssistantLanguage.TURKISH else "Bilge (Ctrl+D to quit)")
    while True:
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not command:
            continue
        try:
            print(agent.handle(command).text)
        except ProviderError as error:
            print(f"! {error}", file=sys.stderr)


def models(args: argparse.Namespace) -> int:
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


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="bilge")
    commands = root.add_subparsers(dest="command", required=True)

    chat_command = commands.add_parser("chat", help="talk to Bilge by typing")
    chat_command.add_argument("--provider", choices=sorted(PRESETS))
    chat_command.add_argument("--model")
    chat_command.add_argument("--language", choices=[lang.value for lang in AssistantLanguage])
    chat_command.set_defaults(run=chat)

    models_command = commands.add_parser("models", help="list a provider's models")
    models_command.add_argument("--provider", choices=sorted(PRESETS))
    models_command.set_defaults(run=models)

    use_command = commands.add_parser("use", help="choose the provider and model")
    use_command.add_argument("provider")
    use_command.add_argument("model")
    use_command.add_argument("--base-url")
    use_command.set_defaults(run=use)

    key_command = commands.add_parser("key", help="store or delete a provider's API key")
    key_command.add_argument("provider")
    key_command.add_argument("--delete", action="store_true")
    key_command.set_defaults(run=key)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.run(args)
    except (ProviderError, RuntimeError) as error:
        print(f"! {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
