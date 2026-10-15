"""The text of a document (PDF, Word, OpenDocument, plain text, web page) without opening it in an app."""

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from bilge.core.web import html_text

READABLE = frozenset({"pdf", "txt", "md", "csv", "docx", "odt", "html", "htm", "rtf"})
MAX_PDF_PAGES = 40
# A document's text part beyond this is not something to read aloud; it also keeps a zip bomb from filling memory.
MAX_XML_BYTES = 20_000_000
MAX_TEXT_BYTES = 2_000_000
_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_ODF_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


class UnreadableDocument(Exception):
    pass


def text_of(path: Path) -> str:
    kind = path.suffix.lower().lstrip(".")
    try:
        if kind == "pdf":
            return _pdf(path)
        if kind == "docx":
            return _paragraphs(_xml(path, "word/document.xml"), f"{_WORD}p", f"{_WORD}t")
        if kind == "odt":
            return _odt(_xml(path, "content.xml"))
        if kind in ("html", "htm"):
            return html_text.extract(_read_text(path))
        if kind == "rtf":
            return _rtf(_read_text(path))
        return _read_text(path)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        raise UnreadableDocument(str(error)) from error


def _read_text(path: Path) -> str:
    with path.open("rb") as file:
        return file.read(MAX_TEXT_BYTES).decode("utf-8", errors="replace")


def _pdf(path: Path) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(path)
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join(page.extract_text() or "" for page in pages)
    except PdfReadError as error:
        raise UnreadableDocument(str(error)) from error


def _xml(path: Path, member: str) -> ElementTree.Element:
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo(member).file_size > MAX_XML_BYTES:
            raise UnreadableDocument("Document too large")
        data = archive.read(member)
    # Office documents never need a DTD; refusing one rules out entity expansion and external entities.
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise UnreadableDocument("Document declares entities")
    return ElementTree.fromstring(data)


def _paragraphs(root: ElementTree.Element, paragraph: str, run: str) -> str:
    return "\n".join("".join(node.text or "" for node in p.iter(run)) for p in root.iter(paragraph))


def _odt(root: ElementTree.Element) -> str:
    lines = []
    for element in root.iter():
        if element.tag in (f"{_ODF_TEXT}p", f"{_ODF_TEXT}h"):
            lines.append("".join(element.itertext()))
    return "\n".join(lines)


_RTF_CONTROL = re.compile(r"\\[a-zA-Z]+-?\d* ?|\\'[0-9a-fA-F]{2}|[{}]")


def _rtf(source: str) -> str:
    """Rough: control words and groups are dropped, which leaves the text of simple documents."""
    return _RTF_CONTROL.sub("", source.replace("\\par", "\n"))
