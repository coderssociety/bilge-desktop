import pytest

from bilge.core.language import AssistantLanguage
from bilge.core.spreadsheet.cell_reference import SpreadsheetNumber
from bilge.desktop.calc import CalcError, Location, calc_formula
from bilge.tools.base import ToolError
from bilge.tools.desktop.spreadsheet import SpreadsheetSession, SpreadsheetTool, spoken_number, spreadsheet_tool

TR, EN = AssistantLanguage.TURKISH, AssistantLanguage.ENGLISH
SHEET = Location("file:///home/ayse/butce.ods", "butce.ods", "Sayfa1")


class FakeCalc:
    """A sheet that keeps contents as Calc's API would: formulas with semicolons, numbers as written."""

    def __init__(self, cells=None, running=True):
        self.cells = dict(cells or {})
        self.running = running
        self.writes = []

    def location(self):
        if not self.running:
            raise CalcError("not_running")
        return SHEET

    def formula(self, at, cell):
        return self.cells.get(cell.address, "")

    def shown(self, at, cell):
        content = self.cells.get(cell.address, "")
        if content == "=B2+B1":
            return str(int(self.cells.get("B2", 0)) + int(self.cells.get("B1", 0)))
        if content.startswith("=") and "/0" in content:
            return "#DIV/0!"
        return content

    def set_formula(self, at, cell, formula):
        self.writes.append(("formula", cell.address, formula))
        self.cells[cell.address] = calc_formula(formula)

    def restore(self, at, cell, content):
        self.cells[cell.address] = content

    def set_value(self, at, cell, value):
        self.writes.append(("value", cell.address, value))
        number = value.value if isinstance(value, SpreadsheetNumber) else None
        self.cells[cell.address] = (
            (str(int(number)) if number == int(number) else str(number)) if number is not None else value.value
        )

    def clear(self, at, cell):
        self.cells.pop(cell.address, None)

    def copy(self, at, source, destination):
        self.cells[destination.address] = self.cells.get(source.address, "")

    def values(self, at, reference):
        if reference == "B1:B3":
            return [self.cells.get(f"B{row}", "") for row in (1, 2, 3)]
        return [self.cells.get(reference, "")]


def make(calc, language=TR):
    session = SpreadsheetSession(language)
    return SpreadsheetTool(calc, session, language), session


def ask_and_run(tool, command):
    arguments = {"command": command}
    return tool.question(arguments), tool.run(arguments)


def test_a_spoken_sum_is_written_read_back_and_starts_spreadsheet_mode():
    calc = FakeCalc({"B1": "2", "B2": "3"})
    tool, session = make(calc)
    question, reply = ask_and_run(tool, "D3'e B2 ile B1'i topla")
    assert question is None
    assert reply == "D3: 5."
    assert calc.writes == [("formula", "D3", "=B2+B1")]
    assert session.active


def test_writing_over_a_filled_cell_asks_and_undo_restores_it():
    calc = FakeCalc({"C5": "100"})
    tool, session = make(calc)
    question, reply = ask_and_run(tool, "C5'e 1250 yaz")
    assert question == "C5 dolu, içinde '100' var. Üzerine yazayım mı?"
    assert reply == "C5: 1250."
    assert ask_and_run(tool, "geri al") == (None, "Geri aldım, C5: 100.")
    assert calc.cells["C5"] == "100"
    with pytest.raises(ToolError, match="Geri alınacak"):
        tool.run({"command": "geri al"})


def test_undo_of_a_new_cell_clears_it():
    calc = FakeCalc()
    tool, _ = make(calc)
    ask_and_run(tool, "A1'e Kira yaz")
    assert ask_and_run(tool, "geri al")[1] == "Geri aldım, A1 yine boş."
    assert "A1" not in calc.cells


def test_reading_and_calculating_need_no_question():
    calc = FakeCalc({"B1": "10", "B2": "20", "B3": "12.5"})
    tool, session = make(calc)
    assert ask_and_run(tool, "B2'yi oku") == (None, "B2: 20.")
    assert ask_and_run(tool, "B1'den B3'e kadar toplam kaç") == (None, "Sonuç 42,5.")
    assert not session.active


def test_a_model_formula_is_read_out_before_it_is_written_and_unsafe_ones_are_refused():
    calc = FakeCalc({"C2": "100"})
    tool, _ = make(calc)
    arguments = {"command": "D2'ye KDV'li fiyatı hesapla", "target": "D2", "formula": "=C2*1.2"}
    assert tool.question(arguments) == "D2 hücresine eşittir C2 çarpı 1,2 formülünü yazayım mı?"
    tool.run(arguments)
    assert calc.cells["D2"] == "=C2*1.2"
    unsafe = {"command": "D2'ye kuru getir", "target": "D2", "formula": '=WEBSERVICE("http://x")'}
    assert tool.question(unsafe) is None
    with pytest.raises(ToolError, match="anlayamadım"):
        tool.run(unsafe)


def test_errors_in_the_new_value_are_reported():
    tool, _ = make(FakeCalc())
    arguments = {"command": "x", "target": "E1", "formula": "=1/0"}
    tool.question(arguments)
    assert tool.run(arguments) == "E1 hata veriyor: #DIV/0!. İstersen geri al de."


def test_calc_not_open_is_said_plainly():
    tool, _ = make(FakeCalc(running=False))
    assert tool.question({"command": "D3'e 5 yaz"}) is None
    with pytest.raises(ToolError, match="LibreOffice Calc açık değil"):
        tool.run({"command": "D3'e 5 yaz"})


def test_a_write_that_needs_a_yes_never_runs_unasked():
    tool, _ = make(FakeCalc({"C5": "100"}))
    with pytest.raises(ToolError):
        tool.run({"command": "C5'e 1250 yaz"})


def test_rules_only_claim_undo_and_finish_inside_spreadsheet_mode():
    session = SpreadsheetSession(TR)
    assert session.claims("D3'e B2 ile B1'i topla")
    assert not session.claims("geri al")
    session.active = True
    assert session.claims("geri al") and session.claims("excel modundan çık")
    assert session.accepts("D2'ye KDV'li fiyatı hesapla")
    assert not session.accepts("akşam ne yiyelim")


def test_formulas_get_calcs_separators_and_numbers_are_spoken_locally():
    assert calc_formula('=AVERAGE(B1,B2,"a,b")') == '=AVERAGE(B1;B2;"a,b")'
    assert spoken_number(1250.5, TR) == "1.250,5"
    assert spoken_number(1250.5, EN) == "1,250.5"
    assert spoken_number(3.0, TR) == "3"


def test_the_tool_always_plans_before_running():
    tool = spreadsheet_tool(make(FakeCalc())[0])
    assert tool.confirmation is not None
