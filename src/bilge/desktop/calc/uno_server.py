"""Runs inside a Python that has LibreOffice's `uno` module (the system Python with python3-uno on Linux, or the
Python that comes with LibreOffice) and answers Bilge's requests about the open Calc documents.

One JSON request per line on standard input, one JSON answer per line on standard output. It connects to
LibreOffice over a named pipe, which only this user can open; nothing listens on the network. Kept to the standard
library and Python 3.6, since it runs outside Bilge's own environment.
"""

import json
import sys

# clearContents flags: VALUE, DATETIME, STRING, FORMULA (comments and formatting stay).
_CONTENTS = 1 | 2 | 4 | 16
_SPREADSHEET = "com.sun.star.sheet.SpreadsheetDocument"


class Failure(Exception):
    pass


def connect(pipe):
    import uno

    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    context = resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
    return context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)


def spreadsheets(desktop):
    found = []
    components = desktop.getComponents().createEnumeration()
    while components.hasMoreElements():
        component = components.nextElement()
        if hasattr(component, "supportsService") and component.supportsService(_SPREADSHEET):
            found.append(component)
    return found


def document_key(document):
    return document.getURL() or document.getTitle()


def location(desktop):
    current = desktop.getCurrentComponent()
    documents = spreadsheets(desktop)
    if current is not None and hasattr(current, "supportsService") and current.supportsService(_SPREADSHEET):
        document = current
    elif documents:
        document = documents[0]
    else:
        return None
    sheet = document.getCurrentController().getActiveSheet()
    return {"document": document_key(document), "title": document.getTitle(), "sheet": sheet.getName()}


def sheet_of(desktop, request):
    for document in spreadsheets(desktop):
        if document_key(document) == request["document"]:
            sheets = document.getSheets()
            if not sheets.hasByName(request["sheet"]):
                raise Failure("no_sheet")
            return sheets.getByName(request["sheet"])
    raise Failure("no_document")


def cell(sheet, address):
    return sheet.getCellRangeByName(address)


def values(sheet, reference, limit):
    address = reference
    if not any(character.isdigit() for character in reference):
        # A whole column ("C:C") is cut to the rows in use.
        cursor = sheet.createCursor()
        cursor.gotoEndOfUsedArea(False)
        rows = cursor.getRangeAddress().EndRow + 1
        columns = reference.split(":")
        if len(columns) != 2 or rows > limit:
            raise Failure("too_large")
        address = f"{columns[0]}1:{columns[1]}{rows}"
    data = cell(sheet, address).getDataArray()
    flat = [item for row in data for item in row]
    if len(flat) > limit:
        raise Failure("too_large")
    return [format_value(item) for item in flat]


def format_value(item):
    if isinstance(item, float):
        return repr(int(item)) if item.is_integer() and abs(item) < 1e15 else repr(item)
    return str(item)


def handle(desktop, request):
    operation = request["op"]
    if operation == "location":
        return location(desktop)
    sheet = sheet_of(desktop, request)
    if operation == "formula":
        return cell(sheet, request["cell"]).getFormula()
    if operation == "shown":
        return cell(sheet, request["cell"]).getString()
    if operation == "set_formula":
        cell(sheet, request["cell"]).setFormula(request["formula"])
    elif operation == "set_number":
        cell(sheet, request["cell"]).setValue(float(request["value"]))
    elif operation == "set_text":
        # setString stores text as typed; it is never read as a formula.
        cell(sheet, request["cell"]).setString(request["text"])
    elif operation == "clear":
        cell(sheet, request["cell"]).clearContents(_CONTENTS)
    elif operation == "copy":
        source = cell(sheet, request["source"]).getRangeAddress()
        sheet.copyRange(cell(sheet, request["destination"]).getCellAddress(), source)
    elif operation == "values":
        return values(sheet, request["range"], int(request["limit"]))
    else:
        raise Failure("unknown_operation")
    return None


def main():
    pipe = sys.argv[1]
    desktop = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if desktop is None:
                desktop = connect(pipe)
            answer = {"ok": handle(desktop, request)}
        except Failure as failure:
            answer = {"error": str(failure)}
        except Exception as error:  # noqa: BLE001 - every failure must come back as an answer
            # pyuno names its exception classes in full ("com.sun.star.connection.NoConnectException").
            name = type(error).__name__.rsplit(".", 1)[-1]
            if name in ("NoConnectException", "DisposedException", "RuntimeException"):
                desktop = None
                answer = {"error": "not_connected", "detail": name}
            else:
                answer = {"error": "failed", "detail": f"{name}: {error}"}
        sys.stdout.write(json.dumps(answer) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
