"""Finding and opening files, making folders, moving a file to the trash and reading documents. Everything stays
inside the user's home folder, and nothing is ever deleted permanently."""

import os
import stat
from enum import StrEnum
from pathlib import Path
from typing import Any

from send2trash import send2trash
from send2trash.exceptions import TrashPermissionError

from bilge.core.language import AssistantLanguage
from bilge.core.text import folded
from bilge.desktop import file_search
from bilge.desktop.base import Folders, Opener
from bilge.desktop.process import DesktopError
from bilge.tools import documents
from bilge.tools.base import Risk, Tool, ToolError
from bilge.tools.desktop.common import choice, failure, obj, string_argument, text

MAX_RESULTS = 5
DOCUMENT_CHARACTERS = 6000
# Opening these would run code the user never approved, so they are only shown in the file manager.
_EXECUTABLE_SUFFIXES = frozenset(
    {
        "sh", "bash", "zsh", "fish", "run", "bin", "appimage", "desktop", "deb", "rpm", "flatpakref", "snap", "py",
        "pl", "rb", "jar", "exe", "msi", "bat", "cmd", "ps1", "vbs", "js", "jsx", "mjs", "command", "app", "pyz",
        "php", "jnlp", "flatpakrepo", "url", "lnk", "hta", "reg", "ovpn", "rdp", "html", "htm", "xhtml", "mhtml",
        "svg", "docm", "xlsm", "pptm", "com", "scr", "cpl", "msc", "msix", "msixbundle", "appx", "wsf", "psm1",
        "vbe", "jse", "inf", "gadget", "application",
    }
)  # fmt: skip


# Windows reports every file as executable and runs dozens of kinds of file when opened, so there only these are
# opened; anything else is shown in Explorer.
_OPENED_ON_WINDOWS = frozenset(
    {
        "pdf", "txt", "md", "csv", "rtf", "doc", "docx", "odt", "xls", "xlsx", "ods", "ppt", "pptx", "odp", "epub",
        "jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "tif", "tiff", "mp3", "wav", "flac", "m4a", "aac", "ogg",
        "wma", "mp4", "mkv", "avi", "mov", "webm", "wmv", "zip",
    }
)  # fmt: skip


def _safe_on_windows(name: str) -> bool:
    # "fatura.exe." and "fatura.exe " open as fatura.exe; a colon names a hidden stream.
    trimmed = name.rstrip(" .")
    if ":" in trimmed or trimmed != name:
        return False
    return Path(trimmed).suffix.lower().lstrip(".") in _OPENED_ON_WINDOWS


class FileAction(StrEnum):
    FIND = "find"
    OPEN_FOUND = "openFound"
    OPEN_LATEST_DOWNLOAD = "openLatestDownload"
    OPEN_FOLDER = "openFolder"


class Folder(StrEnum):
    DESKTOP = "desktop"
    DOWNLOADS = "downloads"
    DOCUMENTS = "documents"
    HOME = "home"


_TEXTS = {
    AssistantLanguage.TURKISH: {
        "files": "Dosya bulur, bulunan dosyayı açar, son indirilen dosyayı açar ya da Masaüstü/İndirilenler/Belgeler klasörünü açar.",
        "query": "'find' ve 'openFound' için dosya adında geçen kelimeler",
        "folder": "'openFolder' için klasör",
        "no_query": "Aranacak dosya adı belirtilmedi.",
        "none_found": "'{query}' ile eşleşen dosya bulunamadı.",
        "found": "Bulunan dosyalar: {files}",
        "downloads_empty": "İndirilenler klasörü boş.",
        "opened": "{name} açıldı.",
        "revealed": "{name} çalıştırılabilir bir dosya; güvenlik için açmadım, dosya yöneticisinde gösterdim.",
        "create": "Masaüstünde, Belgeler'de ya da İndirilenler'de adı verilen yeni bir klasör oluşturur.",
        "create_name": "Klasörün adı",
        "location": "Belirtilmediyse desktop",
        "bad_name": "Bu adla klasör oluşturamam.",
        "exists": "{place} '{name}' adında bir klasör zaten var.",
        "created": "{place} '{name}' klasörünü oluşturdum.",
        "places": {"desktop": "Masaüstü'nde", "documents": "Belgeler'de", "downloads": "İndirilenler'de"},
        "trash": "Adı söylenen bir dosyayı çöp kutusuna taşır (kalıcı silmez).",
        "trash_query": "Dosya adında geçen kelimeler, örn. 'eski fatura'",
        "trash_question": "{location} içindeki '{name}' dosyasını çöp kutusuna taşıyayım mı?",
        "trashed": "'{name}' çöp kutusuna taşındı. Gerekirse oradan geri alabilirsin.",
        "trash_failed": "'{name}' çöp kutusuna taşınamadı.",
        "read": "Bir belgeyi (PDF, metin, Word, OpenDocument) açmadan okur; özetler ya da içeriğiyle ilgili soruyu yanıtlar.",
        "read_query": "Belge adında geçen kelimeler. 'Son indirdiğim PDF' gibi isteklerde yalnızca türü yaz ('pdf', 'word'); tür de yoksa boş bırak",
        "no_document": "'{query}' adında okunabilir bir belge bulamadım.",
        "no_download": "İndirilenler'de okunabilir bir belge bulamadım.",
        "empty_document": "'{name}' içinde okunabilir yazı yok.",
        "scanned_pdf": "'{name}' taranmış bir belge gibi: içinde yazı değil yalnızca sayfa görüntüleri var, o yüzden okuyamıyorum.",
        "unreadable": "'{name}' okunamadı.",
        "document": "Belge: {name}\n{text}",
    },
    AssistantLanguage.ENGLISH: {
        "files": "Finds files, opens a found file, opens the latest download, or opens the Desktop, Downloads or Documents folder.",
        "query": "For 'find' and 'openFound': words in the file name",
        "folder": "For 'openFolder': the folder",
        "no_query": "No file name was given.",
        "none_found": "No file matches '{query}'.",
        "found": "Found: {files}",
        "downloads_empty": "The Downloads folder is empty.",
        "opened": "Opened {name}.",
        "revealed": "{name} is a program; for safety I didn't open it, I showed it in the file manager.",
        "create": "Creates a new folder with the given name on the Desktop, in Documents or in Downloads.",
        "create_name": "The folder's name",
        "location": "desktop unless said otherwise",
        "bad_name": "I can't make a folder with that name.",
        "exists": "There's already a folder called '{name}' {place}.",
        "created": "I made the folder '{name}' {place}.",
        "places": {"desktop": "on the Desktop", "documents": "in Documents", "downloads": "in Downloads"},
        "trash": "Moves a named file to the trash (never deletes permanently).",
        "trash_query": "Words in the file name, e.g. 'old invoice'",
        "trash_question": "Shall I move '{name}' in {location} to the trash?",
        "trashed": "Moved '{name}' to the trash. You can restore it from there.",
        "trash_failed": "Couldn't move '{name}' to the trash.",
        "read": "Reads a document (PDF, text, Word, OpenDocument) without opening it, to summarize it or answer a question about it.",
        "read_query": "Words in the document's name. For 'the PDF I just downloaded' give only the type ('pdf', 'word'); otherwise leave empty",
        "no_document": "I couldn't find a readable document called '{query}'.",
        "no_download": "I couldn't find a readable document in Downloads.",
        "empty_document": "There's no readable text in '{name}'.",
        "scanned_pdf": "'{name}' looks like a scan: it holds pictures of pages rather than text, so I can't read it.",
        "unreadable": "'{name}' couldn't be read.",
        "document": "Document: {name}\n{text}",
    },
}

_TYPE_WORDS = {
    "pdf": {"pdf"}, "word": {"docx", "odt"}, "belge": {"docx", "odt", "pdf"}, "metin": {"txt", "md", "rtf"},
    "text": {"txt", "md", "rtf"}, "tablo": {"csv"}, "document": {"docx", "odt", "pdf"},
}  # fmt: skip


class FileTools:
    def __init__(self, folders: Folders, opener: Opener, language: AssistantLanguage):
        self.folders = folders
        self.opener = opener
        self.language = language
        self.texts = _TEXTS[language]
        # The file named in a trash question, so the one moved is exactly the one the user agreed to.
        self._pending_trash: dict[str, Path] = {}

    def roots(self) -> list[Path]:
        return [self.folders.desktop(), self.folders.documents(), self.folders.downloads(), self.folders.home()]

    def find(self, query: str, limit: int = MAX_RESULTS) -> list[Path]:
        # A link inside the home folder can point anywhere (~/.ssh); only files that really live here count.
        home = self.folders.home().resolve()
        found = file_search.find(query, self.roots(), limit * 2)
        return [path for path in found if path.resolve().is_relative_to(home)][:limit]

    def location(self, path: Path) -> str:
        """ "~/Belgeler", written the same way on every system since it is read aloud."""
        try:
            relative = path.parent.relative_to(self.folders.home()).as_posix()
        except ValueError:
            return str(path.parent)
        return "~" if relative == "." else f"~/{relative}"

    def folder(self, name: str) -> Path:
        return {
            Folder.DESKTOP: self.folders.desktop, Folder.DOWNLOADS: self.folders.downloads,
            Folder.DOCUMENTS: self.folders.documents,
        }.get(name, self.folders.home)()  # fmt: skip

    def open(self, path: Path) -> str:
        try:
            if is_executable(path):
                self.opener.reveal(path)
                return self.texts["revealed"].format(name=path.name)
            self.opener.open(str(path))
        except DesktopError as error:
            raise failure(error, self.language) from error
        return self.texts["opened"].format(name=path.name)

    def latest_download(self) -> Path | None:
        try:
            items = [p for p in self.folders.downloads().iterdir() if not p.name.startswith(".")]
        except OSError:
            return None
        return next(iter(file_search.newest_first(items)), None)

    # Tools

    def files(self, arguments: dict[str, Any]) -> str:
        texts = self.texts
        action = string_argument(arguments, "action")
        query = string_argument(arguments, "query")
        if action in (FileAction.FIND, FileAction.OPEN_FOUND):
            if not query:
                raise ToolError(texts["no_query"])
            found = self.find(query)
            if not found:
                return texts["none_found"].format(query=query)
            if action == FileAction.OPEN_FOUND:
                return self.open(found[0])
            listed = "; ".join(f"{p.name} ({self.location(p)})" for p in found)
            return texts["found"].format(files=listed)
        if action == FileAction.OPEN_LATEST_DOWNLOAD:
            latest = self.latest_download()
            return self.open(latest) if latest else texts["downloads_empty"]
        return self.open(self.folder(string_argument(arguments, "folder")))

    def create_folder(self, arguments: dict[str, Any]) -> str:
        texts = self.texts
        name = string_argument(arguments, "name")
        if not name or name.startswith(".") or any(c in name for c in "/\\:\0") or len(name) > 120:
            raise ToolError(texts["bad_name"])
        location = string_argument(arguments, "location") or Folder.DESKTOP
        if location not in texts["places"]:
            location = Folder.DESKTOP
        place = texts["places"][location]
        folder = self.folder(location) / name
        if folder.exists():
            return texts["exists"].format(place=place, name=name)
        try:
            folder.mkdir()
        except OSError as error:
            raise failure(DesktopError(str(error)), self.language) from error
        return texts["created"].format(place=place, name=name)

    def trash_question(self, arguments: dict[str, Any]) -> str | None:
        # A file named in an earlier, declined question must not be moved by a later call that asks nothing.
        self._pending_trash = {}
        query = string_argument(arguments, "query")
        found = self.find(query, limit=1) if query else []
        if not found:
            return None
        self._pending_trash = {query: found[0]}
        return self.texts["trash_question"].format(location=self.location(found[0]), name=found[0].name)

    def trash(self, arguments: dict[str, Any]) -> str:
        query = string_argument(arguments, "query")
        file = self._pending_trash.pop(query, None)
        if file is None:
            # Only a file the user heard named and agreed to is moved.
            raise ToolError(self.texts["none_found"].format(query=query))
        try:
            send2trash(file)
        except (OSError, TrashPermissionError) as error:
            raise ToolError(self.texts["trash_failed"].format(name=file.name)) from error
        return self.texts["trashed"].format(name=file.name)

    def read_document(self, arguments: dict[str, Any]) -> str:
        texts = self.texts
        query = string_argument(arguments, "query")
        file = self._locate_document(query)
        if file is None:
            raise ToolError(texts["no_document"].format(query=query) if query else texts["no_download"])
        try:
            content = documents.text_of(file).strip()
        except documents.UnreadableDocument as error:
            raise ToolError(texts["unreadable"].format(name=file.name)) from error
        if not content:
            empty = "scanned_pdf" if file.suffix.lower() == ".pdf" else "empty_document"
            raise ToolError(texts[empty].format(name=file.name))
        return texts["document"].format(name=file.name, text=content[:DOCUMENT_CHARACTERS])

    def _locate_document(self, query: str) -> Path | None:
        """A name search first. Phrasings like "son indirilen PDF" name no file, so they fall back to the newest
        download of the mentioned type (or of any readable type)."""
        if query:
            for path in self.find(query, limit=20):
                if path.suffix.lower().lstrip(".") in documents.READABLE:
                    return path
        words = folded(query).split()
        wanted: set[str] = set()
        for word in words:
            for prefix, kinds in _TYPE_WORDS.items():
                if word.startswith(prefix):
                    wanted |= kinds
        mentions_download = any(w.startswith(("indir", "download")) or w in ("son", "latest", "last") for w in words)
        if query and not wanted and not mentions_download:
            return None
        kinds = wanted or documents.READABLE
        try:
            downloads = list(self.folders.downloads().iterdir())
        except OSError:
            return None
        return next((p for p in file_search.newest_first(downloads) if p.suffix.lower().lstrip(".") in kinds), None)


def is_executable(path: Path) -> bool:
    if os.name == "nt":
        return not _safe_on_windows(path.name)
    if path.suffix.lower().lstrip(".") in _EXECUTABLE_SUFFIXES:
        return True
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) and os.access(path, os.X_OK)


def file_tools(folders: Folders, opener: Opener, language: AssistantLanguage) -> list[Tool]:
    tools = FileTools(folders, opener, language)
    texts = tools.texts
    return [
        Tool(
            "files",
            texts["files"],
            run=tools.files,
            parameters=obj(
                ["action"],
                action=choice(FileAction, ""),
                query=text(texts["query"]),
                folder=choice(Folder, texts["folder"]),
            ),
            # Names of downloaded files are chosen by whoever sent them.
            untrusted_output=lambda arguments: arguments.get("action") == FileAction.FIND,
        ),
        Tool(
            "createFolder",
            texts["create"],
            run=tools.create_folder,
            parameters=obj(
                ["name"],
                name=text(texts["create_name"]),
                location=choice(["desktop", "documents", "downloads"], texts["location"]),
            ),
        ),
        Tool(
            "moveFileToTrash",
            texts["trash"],
            run=tools.trash,
            risk=Risk.CONFIRM,
            parameters=obj(["query"], query=text(texts["trash_query"])),
            confirmation=tools.trash_question,
        ),
        Tool(
            "readDocument",
            texts["read"],
            run=tools.read_document,
            untrusted_output=True,
            parameters=obj(query=text(texts["read_query"])),
        ),
    ]
