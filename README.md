# Bilge for Windows and Linux

A voice assistant that speaks Turkish and English, for Windows and Linux. It is the sibling of
[Bilge for macOS](https://github.com/coderssociety/bilge-assistant): the same assistant and the same rules
(say “Bilge”, it asks before anything risky), rebuilt in Python because the Mac version is made of
Apple-only parts.

Unlike the Mac version, the language model can be a hosted API as well as a local one, chosen per setup:

| | Local | Hosted API |
|---|---|---|
| Language model | Ollama, LM Studio, llama.cpp | OpenAI, Anthropic, Google Gemini, OpenRouter, Groq, DeepSeek |

API keys are kept in the system's key store (Windows Credential Manager, the Secret Service on Linux), never
in a plain file.

## Status

Work in progress. Phase 1 of 5 is done:

1. **Core** (done): the Turkish and English parsers from the Mac version with the same test cases, the
   tool-calling agent with confirmations and prompt-injection rules, and a text chat to try it.
2. Voice: microphone, wake word, speech recognition, the Supertonic-3 voice, interrupting.
3. Linux tools: apps, volume, media, files, dictation, calendar, LibreOffice Calc.
4. Windows tools: the same, plus Excel and Outlook.
5. Tray app, settings, setup, installers.

## Trying the text chat

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run bilge use lmstudio <model id>       # or: openai, anthropic, gemini, openrouter, groq, deepseek, ollama
uv run bilge key openai                    # hosted providers only; stored in the system key store
uv run bilge chat
```

`uv run bilge models` lists the chosen provider's models. Tools so far: time and date, calculator,
weather, exchange rates, news headlines, reading a web page, and memory (“remember that…”, “forget…”).

## Development

```bash
uv run pytest
uv run ruff check src tests && uv run ruff format --check src tests
```

`bench/` holds the command sets used to measure routing in the Mac version.

## License

GPL-3.0, see [LICENSE](LICENSE).
