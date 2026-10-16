import pytest

from bilge.desktop import hotkey
from bilge.desktop.hotkey.shortcut import InvalidShortcut, parse


@pytest.mark.parametrize(
    ("text", "windows", "x11", "portal"),
    [
        ("Ctrl+Shift+B", 0x42, "b", "CTRL+SHIFT+b"),
        ("Meta+Alt+B", 0x42, "b", "ALT+LOGO+b"),
        ("Ctrl+Alt+F9", 0x78, "F9", "CTRL+ALT+F9"),
        ("Meta+Shift+F9", 0x78, "F9", "SHIFT+LOGO+F9"),
        ("Ctrl+Space", 0x20, "space", "CTRL+space"),
        ("Alt+7", 0x37, "7", "ALT+7"),
        ("F12", 0x7B, "F12", "F12"),
        ("Ctrl+PgDown", 0x22, "Next", "CTRL+Next"),
        ("Pause", 0x13, "Pause", "Pause"),
    ],
)
def test_names_the_key_for_each_system(text: str, windows: int, x11: str, portal: str) -> None:
    shortcut = parse(text)
    assert shortcut.windows_key == windows
    assert shortcut.x11_key == x11
    assert shortcut.portal_trigger == portal


def test_writes_modifiers_in_a_fixed_order() -> None:
    assert parse("Shift+Alt+Ctrl+F2").text == "Ctrl+Alt+Shift+F2"
    assert parse("Win+K").modifiers == frozenset({"meta"})


@pytest.mark.parametrize(
    "text",
    [
        "",
        "B",
        "Shift+B",
        "Space",
        "Ctrl+",
        "Ctrl++",
        "Ctrl+Ctrl+B",
        "Hyper+B",
        "Ctrl+Ü",
        "Ctrl+Alt+Enter",
        "Ctrl+Alt+BB",
        "Ctrl+Alt+Q",
        "Ctrl+Alt+Shift+2",
    ],
)
def test_refuses_combinations_that_would_take_typing_or_cannot_be_registered(text: str) -> None:
    with pytest.raises(InvalidShortcut):
        parse(text)


def test_an_invalid_combination_is_reported_as_such() -> None:
    with pytest.raises(hotkey.HotkeyError) as caught:
        hotkey.register("Shift+B", lambda: None)
    assert caught.value.reason == "invalid"


def test_wayland_is_recognised(monkeypatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert not hotkey.is_wayland()
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert hotkey.is_wayland()
