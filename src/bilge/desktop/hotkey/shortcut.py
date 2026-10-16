"""A key combination as the settings window writes it ("Ctrl+Alt+B"), and what each system calls those keys."""

from dataclasses import dataclass

MODIFIERS = ("ctrl", "alt", "shift", "meta")
_FUNCTION_KEYS = tuple(f"F{number}" for number in range(1, 25))
# Qt's name → (Windows virtual key, X11 keysym name).
_NAMED_KEYS = {
    "Space": (0x20, "space"), "Pause": (0x13, "Pause"), "Ins": (0x2D, "Insert"), "Home": (0x24, "Home"),
    "End": (0x23, "End"), "PgUp": (0x21, "Prior"), "PgDown": (0x22, "Next"), "Left": (0x25, "Left"),
    "Up": (0x26, "Up"), "Right": (0x27, "Right"), "Down": (0x28, "Down"),
}  # fmt: skip
_QT_MODIFIERS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift", "meta": "meta", "win": "meta",
                 "super": "meta"}  # fmt: skip


class InvalidShortcut(ValueError):
    pass


@dataclass(frozen=True)
class Shortcut:
    modifiers: frozenset[str]
    # "B", "7", "F9", or one of the named keys ("Space").
    key: str

    @property
    def text(self) -> str:
        order = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "meta": "Meta"}
        return "+".join([*(order[m] for m in MODIFIERS if m in self.modifiers), self.key])

    @property
    def windows_key(self) -> int:
        if len(self.key) == 1:
            return ord(self.key)
        if self.key in _FUNCTION_KEYS:
            return 0x70 + _FUNCTION_KEYS.index(self.key)
        return _NAMED_KEYS[self.key][0]

    @property
    def x11_key(self) -> str:
        if len(self.key) == 1:
            return self.key.lower()
        if self.key in _FUNCTION_KEYS:
            return self.key
        return _NAMED_KEYS[self.key][1]

    @property
    def portal_trigger(self) -> str:
        """The XDG shortcuts form the desktop portal takes as a suggestion: "CTRL+ALT+b"."""
        names = {"ctrl": "CTRL", "alt": "ALT", "shift": "SHIFT", "meta": "LOGO"}
        return "+".join([*(names[m] for m in MODIFIERS if m in self.modifiers), self.x11_key])


def parse(text: str) -> Shortcut:
    parts = [part.strip() for part in text.split("+")]
    # "Ctrl++" is Ctrl with the plus key, which is not offered.
    if len(parts) < 1 or any(not part for part in parts):
        raise InvalidShortcut(text)
    *modifier_names, key = parts
    modifiers = set()
    for name in modifier_names:
        modifier = _QT_MODIFIERS.get(name.lower())
        if modifier is None or modifier in modifiers:
            raise InvalidShortcut(text)
        modifiers.add(modifier)
    key = key.upper() if len(key) == 1 else key
    plain = len(key) == 1 and (key.isascii() and key.isalnum())
    if not (plain or key in _FUNCTION_KEYS or key in _NAMED_KEYS):
        raise InvalidShortcut(text)
    # A letter, digit or Space on its own, or with Shift alone, is typing; the shortcut would take it from every app.
    if not (modifiers - {"shift"}) and key not in _FUNCTION_KEYS and key not in ("Pause",):
        raise InvalidShortcut(text)
    # Windows reads AltGr as Ctrl+Alt: Ctrl+Alt+Q would take "@" from Turkish keyboards (and E "€", T "₺").
    if {"ctrl", "alt"} <= modifiers and "meta" not in modifiers and plain:
        raise InvalidShortcut(text)
    return Shortcut(frozenset(modifiers), key)
