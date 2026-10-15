import pytest

from bilge.core.tools.app_name_matcher import App, AppNameMatcher

matcher = AppNameMatcher(
    [
        App("safari", ("Safari",)),
        App("calendar", ("Takvim", "Calendar")),
        App("calculator", ("Hesap Makinesi", "Calculator")),
        App("word", ("Microsoft Word",)),
        App("vscode", ("Visual Studio Code",)),
        App("xcode", ("Xcode",)),
        App("spotify", ("Spotify",)),
        App("music", ("Müzik", "Music")),
        App("mail", ("Mail",)),
    ]
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("safari", "safari"),
        ("Safari'yi", "safari"),
        ("takvim", "calendar"),
        ("Calendar", "calendar"),
        ("hesap makinesi", "calculator"),
        ("hesap makinesini", "calculator"),
        ("word", "word"),
        ("spotifay", "spotify"),
        ("Xcode", "xcode"),
        ("müziği", "music"),
        ("mail uygulaması", "mail"),
        ("visual studio code", "vscode"),
    ],
)
def test_finds_apps_by_localized_name_english_name_suffixes_and_near_misses(query: str, expected: str) -> None:
    app = matcher.best_match(query)
    assert app is not None
    assert app.id == expected


@pytest.mark.parametrize("query", ["photoshop", "", "uygulama"])
def test_returns_none_when_nothing_is_close(query: str) -> None:
    assert matcher.best_match(query) is None
