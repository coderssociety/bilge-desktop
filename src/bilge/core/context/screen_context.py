from dataclasses import dataclass

from bilge.core.context.context_intent import Kind


@dataclass(frozen=True)
class ScreenContext:
    """What the user may be pointing at when they say "bu" or "şu": captured when the command is heard.
    URLs are kept as strings (file paths or web addresses)."""

    selected_text: str | None = None
    selected_files: tuple[str, ...] = ()
    page_url: str | None = None
    page_title: str | None = None
    # The file shown in the front window (Preview, TextEdit, Word…).
    document_url: str | None = None


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Files:
    urls: tuple[str, ...]


@dataclass(frozen=True)
class Page:
    url: str
    title: str | None


@dataclass(frozen=True)
class Document:
    url: str


ContextItem = Text | Files | Page | Document


def resolve(wanted: Kind | None, screen: ScreenContext) -> ContextItem | None:
    """The named kind when the user said one ("bu dosya", "bu sayfa"); otherwise the most specific
    thing on screen: a selection, then selected files, then the page, then the open document."""
    trimmed = screen.selected_text.strip() if screen.selected_text is not None else ""
    text = Text(trimmed) if trimmed else None
    files = Files(screen.selected_files) if screen.selected_files else None
    page = Page(screen.page_url, title=screen.page_title) if screen.page_url is not None else None
    document = Document(screen.document_url) if screen.document_url is not None else None
    match wanted:
        case Kind.TEXT:
            return text
        case Kind.PAGE:
            return page
        case Kind.FILE:
            if files is not None:
                return files
            return Files((screen.document_url,)) if screen.document_url is not None else None
        case Kind.DOCUMENT:
            return document or files
        case None:
            return text or files or page or document
