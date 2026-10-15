"""Reading and filling the clipboard, and reading the selected text. What was copied or selected may come from
anywhere (a web page, an e-mail), so it counts as untrusted."""

from collections.abc import Callable
from typing import Any

from bilge.core.language import AssistantLanguage
from bilge.desktop.base import Clipboard
from bilge.desktop.process import DesktopError
from bilge.tools.base import Tool, ToolError
from bilge.tools.desktop.common import failure, obj, string_argument, text

CLIPBOARD_CHARACTERS = 1500
SELECTION_CHARACTERS = 6000

_TEXTS = {
    AssistantLanguage.TURKISH: {
        "read": "Panodaki (kopyalanan) metni okur.",
        "empty": "Panoda metin yok.",
        "content": "Panodaki metin: {text}",
        "copy": "Söylenen metni ya da az önceki yanıtı panoya kopyalar ('bunu kopyala', 'şunu panoya al: ...').",
        "copy_text": "Kopyalanacak metin; 'bunu', 'az önceki yanıtı' deniyorsa boş bırak",
        "nothing_to_copy": "Panoya ne kopyalayacağımı anlayamadım.",
        "copied": "Panoya kopyaladım.",
        "selection": "Öndeki uygulamada seçili (işaretlenmiş) metni okur; özetler, çevirir ya da açıklar.",
        "request": "Seçili metinle ne yapılacağı, örn. 'özetle', 'İngilizceye çevir', 'oku'",
        "no_selection": "Seçili bir metin bulamadım.",
    },
    AssistantLanguage.ENGLISH: {
        "read": "Reads the text on the clipboard (what was copied).",
        "empty": "There's no text on the clipboard.",
        "content": "The clipboard says: {text}",
        "copy": "Copies the given text, or the previous reply, to the clipboard ('copy that', 'put this on the clipboard: ...').",
        "copy_text": "The text to copy; leave empty for 'this' or 'the previous answer'",
        "nothing_to_copy": "I didn't get what to copy.",
        "copied": "Copied to the clipboard.",
        "selection": "Reads the text selected in the app in front, to summarize, translate or explain it.",
        "request": "What to do with the selection, e.g. 'summarize', 'translate to Turkish', 'read'",
        "no_selection": "I couldn't find any selected text.",
    },
}


def _clipped(content: str, limit: int) -> str:
    return content if len(content) <= limit else content[:limit] + "…"


def clipboard_tools(
    clipboard: Clipboard, language: AssistantLanguage, last_reply: Callable[[], str | None]
) -> list[Tool]:
    texts = _TEXTS[language]

    def read(_: dict[str, Any]) -> str:
        try:
            content = clipboard.read()
        except DesktopError as error:
            raise failure(error, language) from error
        if not content.strip():
            return texts["empty"]
        return texts["content"].format(text=_clipped(content, CLIPBOARD_CHARACTERS))

    def copy(arguments: dict[str, Any]) -> str:
        content = string_argument(arguments, "text") or (last_reply() or "").strip()
        if not content:
            raise ToolError(texts["nothing_to_copy"])
        try:
            clipboard.write(content)
        except DesktopError as error:
            raise failure(error, language) from error
        return texts["copied"]

    def selection(_: dict[str, Any]) -> str:
        try:
            content = clipboard.selection().strip()
        except DesktopError as error:
            raise failure(error, language) from error
        if not content:
            raise ToolError(texts["no_selection"])
        return _clipped(content, SELECTION_CHARACTERS)

    return [
        Tool("readClipboard", texts["read"], run=read, untrusted_output=True),
        Tool("copyToClipboard", texts["copy"], run=copy, parameters=obj(text=text(texts["copy_text"]))),
        Tool(
            "readSelection",
            texts["selection"],
            run=selection,
            parameters=obj(request=text(texts["request"])),
            untrusted_output=True,
        ),
    ]
