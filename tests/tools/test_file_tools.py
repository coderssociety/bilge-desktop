import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from bilge.core.language import AssistantLanguage
from bilge.desktop import file_search
from bilge.tools import documents
from bilge.tools.base import ToolError
from bilge.tools.desktop.files import FileTools, file_tools, is_executable

TR = AssistantLanguage.TURKISH


@pytest.fixture
def home(tmp_path):
    for folder in ("Masaüstü", "Belgeler", "İndirilenler", ".cache", "proje/node_modules"):
        (tmp_path / folder).mkdir(parents=True)
    (tmp_path / "Belgeler" / "Kira Sözleşmesi 2026.txt").write_text("Kira bedeli 20.000 TL.", encoding="utf-8")
    (tmp_path / ".cache" / "kira-cache.txt").write_text("gizli")
    (tmp_path / "proje" / "node_modules" / "kira.js").write_text("x")
    return tmp_path


class Opener:
    def __init__(self):
        self.opened, self.revealed = [], []

    def open(self, target):
        self.opened.append(target)

    def reveal(self, path):
        self.revealed.append(path)


def folders(home):
    return SimpleNamespace(home=lambda: home, desktop=lambda: home / "Masaüstü", documents=lambda: home / "Belgeler",
                           downloads=lambda: home / "İndirilenler", pictures=lambda: home / "Resimler")  # fmt: skip


def tools_for(home, opener=None):
    return {tool.name: tool for tool in file_tools(folders(home), opener or Opener(), TR)}


def test_search_ignores_case_turkish_letters_hidden_and_bulky_folders(home):
    found = file_search.find("kira sozlesmesi", [home], 5)
    assert [p.name for p in found] == ["Kira Sözleşmesi 2026.txt"]


def test_find_and_open(home):
    opener = Opener()
    tools = tools_for(home, opener)
    assert tools["files"].run({"action": "find", "query": "kira"}) == (
        "Bulunan dosyalar: Kira Sözleşmesi 2026.txt (~/Belgeler)"
    )
    assert tools["files"].run({"action": "openFound", "query": "kira"}) == "Kira Sözleşmesi 2026.txt açıldı."
    assert opener.opened == [str(home / "Belgeler" / "Kira Sözleşmesi 2026.txt")]


def test_programs_are_shown_not_run(home):
    script = home / "İndirilenler" / "kur.sh"
    script.write_text("#!/bin/sh\n")
    opener = Opener()
    reply = tools_for(home, opener)["files"].run({"action": "openLatestDownload"})
    assert "güvenlik için açmadım" in reply
    assert opener.revealed == [script] and opener.opened == []
    assert is_executable(home / "app.AppImage")


def test_folder_names_are_checked(home):
    create = tools_for(home)["createFolder"]
    assert create.run({"name": "Faturalar", "location": "documents"}) == "Belgeler'de 'Faturalar' klasörünü oluşturdum."
    assert (home / "Belgeler" / "Faturalar").is_dir()
    for bad in ("../dışarı", ".gizli", ""):
        with pytest.raises(ToolError):
            create.run({"name": bad})


def test_trash_moves_only_the_file_named_in_the_question(home, monkeypatch):
    trashed = []
    monkeypatch.setattr("bilge.tools.desktop.files.send2trash", lambda path: trashed.append(path))
    tools = FileTools(folders(home), Opener(), TR)
    question = tools.trash_question({"query": "kira"})
    assert question == "~/Belgeler içindeki 'Kira Sözleşmesi 2026.txt' dosyasını çöp kutusuna taşıyayım mı?"
    assert tools.trash({"query": "kira"}).startswith("'Kira Sözleşmesi 2026.txt' çöp kutusuna taşındı")
    assert trashed == [home / "Belgeler" / "Kira Sözleşmesi 2026.txt"]
    # Without a question first, nothing is moved.
    with pytest.raises(ToolError):
        tools.trash({"query": "kira"})
    assert tools.trash_question({"query": "yok böyle dosya"}) is None


def write_docx(path: Path, paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")  # fmt: skip
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


def write_odt(path: Path, paragraphs):
    body = "".join(f"<text:p>{text}</text:p>" for text in paragraphs)
    xml = ('<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
           f"<office:body><office:text>{body}</office:text></office:body></office:document-content>")  # fmt: skip
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("content.xml", xml)


def write_pdf(path: Path, line: str):
    stream = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def test_documents_are_read_without_opening_them(tmp_path):
    write_docx(tmp_path / "a.docx", ["Birinci paragraf", "İkinci paragraf"])
    write_odt(tmp_path / "b.odt", ["Toplantı notları"])
    write_pdf(tmp_path / "c.pdf", "Invoice total 1250")
    assert documents.text_of(tmp_path / "a.docx") == "Birinci paragraf\nİkinci paragraf"
    assert documents.text_of(tmp_path / "b.odt") == "Toplantı notları"
    assert "Invoice total 1250" in documents.text_of(tmp_path / "c.pdf")
    (tmp_path / "broken.docx").write_bytes(b"not a zip")
    with pytest.raises(documents.UnreadableDocument):
        documents.text_of(tmp_path / "broken.docx")


def test_latest_downloaded_pdf_is_found_by_type(home):
    write_pdf(home / "İndirilenler" / "fatura.pdf", "Total 99")
    read = tools_for(home)["readDocument"]
    assert read.untrusted_output
    assert read.run({"query": "son indirdiğim pdf"}).startswith("Belge: fatura.pdf\n")
    with pytest.raises(ToolError, match="okunabilir bir belge bulamadım"):
        read.run({"query": "olmayan rapor"})


def test_a_pdf_without_text_is_said_to_be_a_scan(home):
    write_pdf(home / "İndirilenler" / "tarama.pdf", "")
    with pytest.raises(ToolError, match="taranmış bir belge"):
        tools_for(home)["readDocument"].run({"query": "son indirdiğim pdf"})


def test_a_declined_trash_question_leaves_nothing_to_move(home, monkeypatch):
    trashed = []
    monkeypatch.setattr("bilge.tools.desktop.files.send2trash", lambda path: trashed.append(path))
    tools = FileTools(folders(home), Opener(), TR)
    assert tools.trash_question({"query": "kira"})
    # The user said no; the file is then renamed, so the next question finds nothing and asks nothing.
    (home / "Belgeler" / "Kira Sözleşmesi 2026.txt").rename(home / "Belgeler" / "arsiv.txt")
    assert tools.trash_question({"query": "kira"}) is None
    with pytest.raises(ToolError):
        tools.trash({"query": "kira"})
    assert trashed == []


def test_links_out_of_the_home_folder_are_not_found(home, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "id_rsa.txt"
    outside.write_text("secret")
    try:
        (home / "Belgeler" / "anahtar.txt").symlink_to(outside)
    except OSError:
        pytest.skip("making links needs a privilege on this system")
    assert FileTools(folders(home), Opener(), TR).find("anahtar") == []


def test_documents_with_entity_declarations_are_refused(tmp_path):
    with zipfile.ZipFile(tmp_path / "bomb.docx", "w") as archive:
        archive.writestr("word/document.xml", '<!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
    with pytest.raises(documents.UnreadableDocument):
        documents.text_of(tmp_path / "bomb.docx")


def test_windows_opens_only_documents_and_media():
    from bilge.tools.desktop.files import _safe_on_windows

    assert _safe_on_windows("rapor.pdf") and _safe_on_windows("tatil.JPG")
    for name in ("kur.exe", "fatura.exe.", "fatura.pdf ", "belge.pdf:gizli", "makro.docm", "kısayol.lnk", "x.pif"):
        assert not _safe_on_windows(name), name
