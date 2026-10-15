"""Live edits in the open spreadsheet (Excel or LibreOffice Calc): "D3'e B2 ile B1'i topla", "C5'e 1250 yaz", "D3'ü oku", "geri al".

Commands the rules understand never reach the language model. In spreadsheet mode, other requests about cells get a
formula from the model, which is checked and read out before it is written. Writing over a filled cell asks first,
and the assistant's own changes can be undone.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from bilge.core.language import AssistantLanguage
from bilge.core.speech import turkish_number_parser
from bilge.core.spreadsheet import spreadsheet_command, spreadsheet_evaluator, spreadsheet_formula
from bilge.core.spreadsheet.cell_reference import CellReference, SpreadsheetValue
from bilge.core.spreadsheet.spreadsheet_command import (
    Clear,
    Copy,
    Evaluate,
    Finish,
    Read,
    SetFormula,
    SetValue,
    SpreadsheetCommand,
    Undo,
)
from bilge.desktop.calc import CalcError, Location
from bilge.tools.base import Risk, Tool, ToolError
from bilge.tools.desktop.common import obj, string_argument, text

EN, TR = AssistantLanguage.ENGLISH, AssistantLanguage.TURKISH
MAX_SPOKEN_CONTENT = 60
MAX_HISTORY = 30


class Calc(Protocol):
    def location(self) -> Location | None: ...

    def formula(self, at: Location, cell: CellReference) -> str: ...

    def shown(self, at: Location, cell: CellReference) -> str: ...

    def set_formula(self, at: Location, cell: CellReference, formula: str) -> None: ...

    def restore(self, at: Location, cell: CellReference, content: str) -> None: ...

    def set_value(self, at: Location, cell: CellReference, value: SpreadsheetValue) -> None: ...

    def clear(self, at: Location, cell: CellReference) -> None: ...

    def copy(self, at: Location, source: CellReference, destination: CellReference) -> None: ...

    def values(self, at: Location, reference: str) -> list[str]: ...


@dataclass(frozen=True)
class Change:
    location: Location
    cell: CellReference
    # The formula or constant the cell held before, empty if it was empty.
    previous: str


@dataclass
class SpreadsheetSession:
    """Whether spreadsheet mode is on, and the assistant's own changes so "geri al" can restore them."""

    language: AssistantLanguage
    # How long spreadsheet mode waits for the next command.
    window: float = 45
    active: bool = False
    history: list[Change] = field(default_factory=list)

    def record(self, change: Change) -> None:
        self.history = [*self.history, change][-MAX_HISTORY:]

    def take_last(self) -> Change | None:
        if not self.history:
            return None
        last, self.history = self.history[-1], self.history[:-1]
        return last

    def command(self, spoken: str) -> SpreadsheetCommand | None:
        """Turkish number words become digits first ("bin iki yüz elli"); English is read as said, since the Turkish
        rules would turn "on" and "one" into 10."""
        digits = turkish_number_parser.digitize(spoken) if self.language is TR else spoken
        return spreadsheet_command.parse(digits, self.language)

    def claims(self, spoken: str) -> bool:
        """Whether a command goes straight to the spreadsheet without the model. Undo and finishing only count in
        spreadsheet mode; "geri al" means other things elsewhere."""
        parsed = self.command(spoken)
        if isinstance(parsed, Undo | Finish):
            return self.active
        return parsed is not None

    def accepts(self, spoken: str) -> bool:
        """In spreadsheet mode, without the wake word: only what is about cells."""
        return self.command(spoken) is not None or spreadsheet_command.mentions_cells(spoken, self.language)


_TEXTS = {
    TR: {
        "description": "Açık Excel ya da LibreOffice Calc tablosunda hücreye formül ya da değer yazar, hücre okur, siler, kopyalar ve hesaplar ('D3'e B2 ile B1'i topla').",
        "command": "Kullanıcının tablo isteği, olduğu gibi",
        "target": "Sonucun yazılacağı hücre, örn. 'D2'; yoksa boş bırak",
        "formula": "Hücreye yazılacak formül; İngilizce fonksiyon adları, ondalık ayırıcı nokta, argüman ayırıcı virgül: '=C2*1.2', '=SUM(B1:B9)'",
        "not_running": "Excel ya da LibreOffice Calc açık değil.",
        "no_document": "Açık bir tablo yok.",
        "no_uno": "LibreOffice'e bağlanamadım. Linux'ta python3-uno paketinin kurulu olması gerekiyor.",
        "too_large": "Bu aralık sesle hesaplamak için çok büyük.",
        "failed": "Tabloda bunu yapamadım.",
        "finished": "Tablo modundan çıktım.",
        "nothing_to_undo": "Geri alınacak bir değişikliğim yok.",
        "undone_empty": "Geri aldım, {cell} yine boş.",
        "undone": "Geri aldım, {cell}: {shown}.",
        "empty": "{cell} boş.",
        "shows": "{cell}: {shown}.",
        "error_value": "{cell} hata veriyor: {shown}. İstersen geri al de.",
        "overwrite": "{cell} dolu, içinde {content} var. Üzerine yazayım mı?",
        "model_formula": "{cell} hücresine {formula} formülünü yazayım mı?",
        "unclear": "Bunu tabloda nasıl yapacağımı anlayamadım. Örneğin 'D3'e B2 ile B1'i topla' diyebilirsin.",
        "not_numbers": "Bunu hesaplayamadım; hücrelerde sayı olmayabilir.",
        "result": "Sonuç {value}.",
        "words": [("=", "eşittir "), ("+", " artı "), ("-", " eksi "), ("*", " çarpı "), ("/", " bölü "), (":", " ile ")],
    },
    EN: {
        "description": "Writes a formula or value into a cell of the open Excel or LibreOffice Calc sheet, reads, clears, copies and calculates cells ('put B2 plus B1 in D3').",
        "command": "The user's spreadsheet request, as said",
        "target": "The cell for the result, e.g. 'D2'; leave empty if none",
        "formula": "The formula to write; English function names, a point for decimals, commas between arguments: '=C2*1.2', '=SUM(B1:B9)'",
        "not_running": "Neither Excel nor LibreOffice Calc is open.",
        "no_document": "There's no spreadsheet open.",
        "no_uno": "I couldn't connect to LibreOffice. On Linux the python3-uno package needs to be installed.",
        "too_large": "That range is too large to calculate by voice.",
        "failed": "I couldn't do that in the sheet.",
        "finished": "I left spreadsheet mode.",
        "nothing_to_undo": "I have no change to undo.",
        "undone_empty": "Undone; {cell} is empty again.",
        "undone": "Undone; {cell}: {shown}.",
        "empty": "{cell} is empty.",
        "shows": "{cell}: {shown}.",
        "error_value": "{cell} shows an error: {shown}. Say undo if you like.",
        "overwrite": "{cell} already holds {content}. Shall I write over it?",
        "model_formula": "Shall I write the formula {formula} in {cell}?",
        "unclear": "I didn't get how to do that in the sheet. You could say, for example, 'put B2 plus B1 in D3'.",
        "not_numbers": "I couldn't calculate that; the cells may not hold numbers.",
        "result": "The result is {value}.",
        "words": [("=", "equals "), ("+", " plus "), ("-", " minus "), ("*", " times "), ("/", " divided by "), (":", " to ")],
    },
}  # fmt: skip


@dataclass(frozen=True)
class Plan:
    """A prepared step: what to ask first, if anything, and how to do it."""

    execute: Callable[[], str]
    question: str | None = None


class SpreadsheetTool:
    def __init__(self, calc: Calc, session: SpreadsheetSession, language: AssistantLanguage):
        self.calc = calc
        self.session = session
        self.language = language
        self.texts = _TEXTS[language]
        # The plan behind the last question, so what runs is what the user heard.
        self._pending: tuple[str, Plan] | None = None

    def question(self, arguments: dict[str, Any]) -> str | None:
        plan = self._plan(arguments)
        self._pending = (_key(arguments), plan)
        return plan.question

    def run(self, arguments: dict[str, Any]) -> str:
        pending, self._pending = self._pending, None
        if pending is not None and pending[0] == _key(arguments):
            return pending[1].execute()
        plan = self._plan(arguments)
        if plan.question:
            # A write that needs a yes never happens without the question having been asked.
            raise ToolError(self.texts["failed"])
        return plan.execute()

    def _plan(self, arguments: dict[str, Any]) -> Plan:
        try:
            command = self.session.command(string_argument(arguments, "command"))
            if command is not None:
                return self._plan_command(command)
            return self._plan_model_formula(arguments)
        except CalcError as error:
            message = self.texts.get(error.reason, self.texts["failed"])
            return Plan(lambda: _raise(message))

    def _plan_command(self, command: SpreadsheetCommand) -> Plan:
        texts = self.texts
        if isinstance(command, Finish):
            return Plan(self._finish)
        if isinstance(command, Undo):
            return Plan(self._undo)
        at = self.calc.location()
        if at is None:
            return Plan(lambda: _raise(texts["no_document"]))
        if isinstance(command, SetFormula):
            return self._writing(at, command.target, lambda: self.calc.set_formula(at, command.target, command.formula))
        if isinstance(command, SetValue):
            return self._writing(at, command.target, lambda: self.calc.set_value(at, command.target, command.value))
        if isinstance(command, Clear):
            return self._writing(at, command.cell, lambda: self.calc.clear(at, command.cell), confirms_overwrite=False)
        if isinstance(command, Copy):
            return self._writing(
                at, command.destination, lambda: self.calc.copy(at, command.source, command.destination)
            )
        if isinstance(command, Read):
            return Plan(lambda: self._guarded(lambda: self._shows(command.cell, self.calc.shown(at, command.cell))))
        if isinstance(command, Evaluate):
            return Plan(lambda: self._guarded(lambda: self._evaluate(at, command.formula)))
        return Plan(lambda: _raise(texts["unclear"]))

    def _plan_model_formula(self, arguments: dict[str, Any]) -> Plan:
        target = CellReference.parse(string_argument(arguments, "target"))
        formula = string_argument(arguments, "formula")
        if target is None or not spreadsheet_formula.is_safe(formula):
            return Plan(lambda: _raise(self.texts["unclear"]))
        at = self.calc.location()
        if at is None:
            return Plan(lambda: _raise(self.texts["no_document"]))
        plan = self._writing(at, target, lambda: self.calc.set_formula(at, target, formula), confirms_overwrite=False)
        # Read out whole: anything the user doesn't hear could be hidden at the end.
        question = self.texts["model_formula"].format(cell=target.address, formula=self._spoken(formula, whole=True))
        return Plan(plan.execute, question)

    def _writing(
        self, at: Location, cell: CellReference, write: Callable[[], None], confirms_overwrite: bool = True
    ) -> Plan:
        """A write that remembers the cell's previous content for undo, asks before replacing something already
        there, and reads the new value back."""
        previous = self.calc.formula(at, cell)

        def act() -> str:
            write()
            self.session.record(Change(at, cell, previous))
            self.session.active = True
            shown = self.calc.shown(at, cell)
            if _is_error(shown):
                return self.texts["error_value"].format(cell=cell.address, shown=shown)
            return self._shows(cell, shown)

        def execute() -> str:
            return self._guarded(act)

        if confirms_overwrite and previous:
            return Plan(execute, self.texts["overwrite"].format(cell=cell.address, content=self._spoken(previous)))
        return Plan(execute)

    def _finish(self) -> str:
        self.session.active = False
        return self.texts["finished"]

    def _undo(self) -> str:
        change = self.session.history[-1] if self.session.history else None
        if change is None:
            raise ToolError(self.texts["nothing_to_undo"])

        def act() -> str:
            if not change.previous:
                self.calc.clear(change.location, change.cell)
                reply = self.texts["undone_empty"].format(cell=change.cell.address)
            else:
                self.calc.restore(change.location, change.cell, change.previous)
                shown = self.calc.shown(change.location, change.cell)
                reply = self.texts["undone"].format(cell=change.cell.address, shown=shown)
            # Only a change actually put back leaves the history; a failed one can be tried again.
            self.session.take_last()
            return reply

        return self._guarded(act)

    def _shows(self, cell: CellReference, shown: str) -> str:
        if not shown:
            return self.texts["empty"].format(cell=cell.address)
        return self.texts["shows"].format(cell=cell.address, shown=shown)

    def _evaluate(self, at: Location, formula: str) -> str:
        values = {ref: self.calc.values(at, ref) for ref in spreadsheet_evaluator.references(formula)}
        result = spreadsheet_evaluator.evaluate(formula, values)
        if result is None:
            raise ToolError(self.texts["not_numbers"])
        return self.texts["result"].format(value=spoken_number(result, self.language))

    def _guarded(self, action: Callable[[], str]) -> str:
        try:
            return action()
        except CalcError as error:
            raise ToolError(self.texts.get(error.reason, self.texts["failed"])) from error

    def _spoken(self, content: str, whole: bool = False) -> str:
        """Formulas read aloud: "=B2+B1" → "eşittir B2 artı B1"."""
        short = content if whole or len(content) <= MAX_SPOKEN_CONTENT else content[:MAX_SPOKEN_CONTENT] + "…"
        if not short.startswith("="):
            return f"'{short}'"
        if self.language is TR:
            short = re.sub(r"(\d)\.(\d)", r"\1,\2", short)
        for symbol, word in self.texts["words"]:
            short = short.replace(symbol, word)
        return short


def _key(arguments: dict[str, Any]) -> str:
    return repr(sorted((k, str(v)) for k, v in arguments.items()))


def _raise(message: str) -> str:
    raise ToolError(message)


def _is_error(shown: str) -> bool:
    """Calc shows errors as "#DIV/0!", "#NAME?" or "Err:502"."""
    return shown.startswith("#") or shown.startswith("Err:")


def spoken_number(value: float, language: AssistantLanguage) -> str:
    """1250.5 → "1.250,5" in Turkish, "1,250.5" in English; at most two decimals."""
    shown = f"{round(value, 2):,.2f}".rstrip("0").rstrip(".")
    if language is TR:
        return shown.translate(str.maketrans({",": ".", ".": ","}))
    return shown


def spreadsheet_tool(tool: SpreadsheetTool) -> Tool:
    texts = tool.texts
    parameters = obj(
        ["command"], command=text(texts["command"]), target=text(texts["target"]), formula=text(texts["formula"])
    )
    # Reads need no question; each plan says whether its write does, so CONFIRM here means "always plan first".
    return Tool(
        "spreadsheet",
        texts["description"],
        run=tool.run,
        parameters=parameters,
        risk=Risk.CONFIRM,
        confirmation=tool.question,
    )
