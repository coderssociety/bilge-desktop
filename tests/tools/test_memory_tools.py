import os

import pytest

from bilge.core.language import AssistantLanguage
from bilge.tools.base import ToolError
from bilge.tools.builtin.memory import memory_tools
from bilge.tools.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "memory.json")


def tools(store, last_reply=None):
    remember, forget, listing = memory_tools(store, AssistantLanguage.TURKISH, lambda: last_reply)
    return remember, forget, listing


def test_the_fact_comes_from_the_sentence_not_the_model(store):
    remember, _, _ = tools(store)
    arguments = remember.refine({"fact": "Kullanıcının eşi Ayşe Hanım"}, "eşimin adının Ayşe olduğunu hatırla")
    assert remember.question(arguments) is None
    assert remember.run(arguments) == "Tamam, hatırlayacağım."
    assert [e.text for e in store.book.entries] == ["eşimin adının Ayşe olduğunu"]
    assert remember.run(arguments) == "Bunu zaten biliyorum."


def test_remembering_the_previous_reply_asks_first(store):
    remember, _, _ = tools(store, last_reply="Toplantı Salı 10'da.")
    arguments = remember.refine({}, "bunu hatırla")
    assert remember.question(arguments) == "Şunu hatırlayayım mı: Toplantı Salı 10'da."
    remember.run(arguments)
    assert store.book.entries[0].text == "Toplantı Salı 10'da"


def test_nothing_to_remember_is_an_error(store):
    remember, _, _ = tools(store)
    with pytest.raises(ToolError):
        remember.run(remember.refine({}, "bunu hatırla"))


def test_forget_names_the_fact_it_found(store):
    _, forget, listing = tools(store)
    store.remember("kahvemi şekersiz içerim")
    assert forget.question({"about": "kahve"}) == "'kahvemi şekersiz içerim' bilgisini unutayım mı?"
    assert forget.run({"about": "kahve"}) == "Unuttum: kahvemi şekersiz içerim."
    assert listing.run({}) == "Hafızamda bir şey yok."


def test_forget_without_a_match_changes_nothing(store):
    _, forget, _ = tools(store)
    store.remember("kahvemi şekersiz içerim")
    assert forget.question({"about": "araba"}) is None
    with pytest.raises(ToolError, match="araba"):
        forget.run({"about": "araba"})
    assert len(store.book.entries) == 1


def test_forget_everything(store):
    _, forget, _ = tools(store)
    store.remember("bir")
    store.remember("iki")
    assert forget.question({"everything": True}) == "Hatırladığım 2 bilginin hepsini sileyim mi?"
    assert forget.run({"everything": True}) == "Hafızamı temizledim, 2 bilgiyi sildim."


def test_the_file_survives_a_restart_and_is_private(store, tmp_path):
    store.remember("kahvemi şekersiz içerim")
    again = MemoryStore(tmp_path / "memory.json")
    assert again.prompt_lines()
    if os.name == "posix":
        assert (tmp_path / "memory.json").stat().st_mode & 0o777 == 0o600


def test_a_damaged_file_is_not_overwritten(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError, match="memory file"):
        MemoryStore(path)
