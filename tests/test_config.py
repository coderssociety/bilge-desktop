import pytest

from bilge import config
from bilge.core.language import AssistantLanguage


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = config.Settings(language="en", model=config.ModelSettings("openrouter", "some/model"))
    config.save_settings(settings, path)
    loaded = config.load_settings(path)
    assert loaded == settings
    assert loaded.assistant_language is AssistantLanguage.ENGLISH


def test_missing_file_gives_defaults(tmp_path):
    assert config.load_settings(tmp_path / "none.json") == config.Settings()


def test_unknown_language_falls_back_to_turkish():
    assert config.Settings(language="xx").assistant_language is AssistantLanguage.TURKISH


def test_broken_file_is_an_error_not_silently_reset(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Could not read"):
        config.load_settings(path)


def test_api_key_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setattr(config.keyring, "get_password", lambda *_: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    assert config.api_key("openrouter") == "from-env"
    assert config.api_key("lmstudio") is None
