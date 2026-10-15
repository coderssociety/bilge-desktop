"""The Calc client and its helper process, with a stand-in `uno` module so no LibreOffice is needed."""

import sys
import textwrap

import pytest

from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetNumber, SpreadsheetText
from bilge.desktop import calc
from bilge.desktop.calc import CalcError, LibreOfficeCalc
from bilge.desktop.process import Runner

FAKE_UNO = textwrap.dedent("""
    class Address:
        def __init__(self, name):
            self.name = name


    class Cell:
        def __init__(self, sheet, name):
            self.sheet, self.name = sheet, name

        def getFormula(self):
            return self.sheet.cells.get(self.name, "")

        def getString(self):
            value = self.sheet.cells.get(self.name, "")
            return value.replace(".", ",") if value[:1].isdigit() else value

        def setFormula(self, formula):
            self.sheet.cells[self.name] = formula

        def setValue(self, value):
            self.sheet.cells[self.name] = repr(value).removesuffix(".0")

        def setString(self, text):
            self.sheet.cells[self.name] = text

        def clearContents(self, flags):
            assert flags == 23
            self.sheet.cells.pop(self.name, None)

        def getRangeAddress(self):
            return Address(self.name)

        def getCellAddress(self):
            return Address(self.name)

        def getDataArray(self):
            first, last = self.name.split(":")
            column = first[0]
            rows = range(int(first[1:]), int(last[1:]) + 1)
            return tuple((float(self.sheet.cells.get(f"{column}{r}", "0")),) for r in rows)


    class Cursor:
        def gotoEndOfUsedArea(self, expand):
            pass

        def getRangeAddress(self):
            class Range:
                EndRow = 2
            return Range()


    class Sheet:
        def __init__(self):
            self.cells = {"B1": "10", "B2": "2.5", "B3": "7"}

        def getName(self):
            return "Sayfa1"

        def getCellRangeByName(self, name):
            return Cell(self, name)

        def copyRange(self, destination, source):
            self.cells[destination.name] = self.cells.get(source.name, "")

        def createCursor(self):
            return Cursor()


    class Sheets:
        def __init__(self):
            self.sheet = Sheet()

        def hasByName(self, name):
            return name == "Sayfa1"

        def getByName(self, name):
            return self.sheet


    class Controller:
        def __init__(self, sheets):
            self.sheets = sheets

        def getActiveSheet(self):
            return self.sheets.sheet


    class Document:
        def __init__(self):
            self.sheets = Sheets()

        def supportsService(self, name):
            return name == "com.sun.star.sheet.SpreadsheetDocument"

        def getURL(self):
            return "file:///home/ayse/butce.ods"

        def getTitle(self):
            return "butce.ods"

        def getSheets(self):
            return self.sheets

        def getCurrentController(self):
            return Controller(self.sheets)


    class Enumeration:
        def __init__(self, items):
            self.items = list(items)

        def hasMoreElements(self):
            return bool(self.items)

        def nextElement(self):
            return self.items.pop(0)


    class Components:
        def __init__(self, items):
            self.items = items

        def createEnumeration(self):
            return Enumeration(self.items)


    class Desktop:
        def __init__(self):
            self.document = Document()

        def getComponents(self):
            return Components([self.document])

        def getCurrentComponent(self):
            return self.document


    class Manager:
        def createInstanceWithContext(self, name, context):
            if name == "com.sun.star.bridge.UnoUrlResolver":
                return Resolver()
            return Desktop()


    class Context:
        ServiceManager = Manager()


    class Resolver:
        def resolve(self, url):
            assert url.startswith("uno:pipe,name=bilge_calc_") and url.endswith(";urp;StarOffice.ComponentContext")
            return Context()


    def getComponentContext():
        return Context()
""")


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "uno.py").write_text(FAKE_UNO, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.setattr(LibreOfficeCalc, "is_running", lambda self: True)
    found = LibreOfficeCalc(Runner(), candidates=[sys.executable])
    yield found
    found.close()


def test_cells_are_read_written_copied_and_cleared_through_the_helper(client):
    at = client.location()
    assert (at.title, at.sheet) == ("butce.ods", "Sayfa1")
    b2, d1 = CellReference.parse("B2"), CellReference.parse("D1")
    assert client.formula(at, b2) == "2.5"
    assert client.shown(at, b2) == "2,5"
    client.set_formula(at, d1, "=AVERAGE(B1,B2)")
    assert client.formula(at, d1) == "=AVERAGE(B1;B2)"
    client.set_value(at, d1, SpreadsheetNumber(1250.0))
    assert client.formula(at, d1) == "1250"
    client.set_value(at, d1, SpreadsheetText("=SUM(A1)"))
    assert client.formula(at, d1) == "=SUM(A1)"
    client.copy(at, b2, d1)
    assert client.formula(at, d1) == "2.5"
    client.clear(at, d1)
    assert client.formula(at, d1) == ""
    assert client.values(at, "B1:B3") == ["10", "2.5", "7"]
    assert client.values(at, "B:B") == ["10", "2.5", "7"]


def test_an_unknown_document_is_an_error_not_a_crash(client):
    gone = calc.Location("file:///gone.ods", "gone.ods", "Sayfa1")
    with pytest.raises(CalcError) as error:
        client.formula(gone, CellReference.parse("A1"))
    assert error.value.reason == "no_document"
    # The helper is still there for the next request.
    assert client.location() is not None


def test_closed_libreoffice_and_missing_uno_are_reported(monkeypatch):
    monkeypatch.setattr(LibreOfficeCalc, "is_running", lambda self: False)
    with pytest.raises(CalcError) as error:
        LibreOfficeCalc(Runner(), candidates=[sys.executable]).location()
    assert error.value.reason == "not_running"
    monkeypatch.setattr(LibreOfficeCalc, "is_running", lambda self: True)
    with pytest.raises(CalcError) as error:
        LibreOfficeCalc(Runner(), candidates=["/nonexistent/python"]).location()
    assert error.value.reason == "no_uno"


def test_a_failing_desktop_program_becomes_a_calc_error(monkeypatch):
    from bilge.desktop.process import DesktopError

    class SlowRunner(Runner):
        def run(self, argv, **_):
            raise DesktopError("python3 timed out")

    monkeypatch.setattr(LibreOfficeCalc, "is_running", lambda self: True)
    with pytest.raises(CalcError) as error:
        LibreOfficeCalc(SlowRunner(), candidates=[sys.executable]).location()
    assert error.value.reason == "failed"


def test_each_session_uses_its_own_pipe():
    assert LibreOfficeCalc(Runner()).pipe != LibreOfficeCalc(Runner()).pipe
