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

Work in progress. Phases 1 to 3 of 5 are done:

1. **Core** (done): the Turkish and English parsers from the Mac version with the same test cases, the
   tool-calling agent with confirmations and prompt-injection rules, and a text chat to try it.
2. **Voice** (done): wake word, speech recognition (Whisper on the computer, or the OpenAI or Groq API), the
   Supertonic-3 voice, echo cancellation so you can cut in, and voice recognition of the owner.
3. **Linux tools** (done): apps, volume, music players, files and documents, typing and dictation, timers,
   calendar and reminders, LibreOffice Calc, system controls.
4. Windows tools: the same, plus Excel and Outlook.
5. Tray app, settings, setup, installers.

## Trying it

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run bilge use lmstudio <model id>       # or: openai, anthropic, gemini, openrouter, groq, deepseek, ollama
uv run bilge key openai                    # hosted providers only; stored in the system key store
uv run bilge chat                          # by typing
uv run bilge listen                        # by voice; downloads the voice models the first time
```

`uv run bilge models` lists the chosen provider's models.

## What it can do on Linux

| | Examples | Uses |
|---|---|---|
| Apps | “Firefox'u aç”, “hesap makinesini kapat”, “açık uygulamalar neler” | the desktop's menu entries, `gio` |
| Sound | “sesi yüzde 30 yap”, “müziği durdur”, “ne çalıyor” | `wpctl`, `pactl` or `amixer`; any MPRIS player |
| Files | “kira sözleşmesini bul”, “son indirdiğim PDF'i özetle”, “eski faturayı çöpe at” | the home folder, the freedesktop trash |
| Typing | “şunu yaz: …”, “dikte modunu başlat” | `xdotool` (X11), `wtype` or `ydotool` (Wayland) |
| Calendar | “yarın neler var”, “cuma 10'da diş hekimi ekle”, “süt almayı işaretle” | CalDAV, or a read-only iCal address |
| Spreadsheet | “D3'e B2 ile B1'i topla”, “C5'e 1250 yaz”, “geri al” | LibreOffice Calc with `python3-uno` |
| System | “ekranı kilitle”, “karanlık modu aç”, “Wi-Fi'ı kapat”, “ekran görüntüsü al”, “pil kaç” | `loginctl`, `gsettings` or Plasma, `nmcli`, the desktop's screenshot tool |
| Clipboard | “panoda ne var”, “seçili metni çevir”, “bunu kopyala” | `wl-clipboard`, `xclip` or `xsel` |
| Other | timers and alarms, opening sites and searches, the daily briefing | |

Moving files to the trash, closing apps, writing over a filled cell, adding to the calendar or turning Wi-Fi off
asks first, and so does anything that could carry text Bilge has read somewhere else. Typing is refused in terminals,
code editors, remote desktops, virtual machines and password managers. GNOME on Wayland doesn't tell other
programs which window is in front, so there Bilge asks before typing.

### Connecting a calendar

```bash
uv run bilge calendar caldav https://cloud.example.org/remote.php/dav --user ayse   # Nextcloud, iCloud, Fastmail…
uv run bilge calendar ics                   # read-only: e.g. Google Calendar's "secret address in iCal format"
uv run bilge calendar off
```

The password (use an app password where the service has them) and the secret address are typed hidden and kept
in the system key store. CalDAV is only spoken to over HTTPS, except a server on the same computer.

## Development

```bash
uv run pytest
uv run ruff check src tests && uv run ruff format --check src tests
```

`bench/` holds the command sets used to measure routing in the Mac version. `scripts/linux-check` runs the
whole suite on Ubuntu, plus tests that drive the real programs (typing, clipboard, sound, an MPRIS player,
notifications, LibreOffice Calc…) on a screenless desktop:

```bash
docker build -t bilge-linux-check scripts/linux-check
docker run --rm -v "$PWD":/src:ro bilge-linux-check
```

## License

GPL-3.0, see [LICENSE](LICENSE).
