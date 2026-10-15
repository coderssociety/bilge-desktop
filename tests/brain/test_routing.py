from datetime import datetime

import pytest

from bilge.brain import fast_path
from bilge.brain.agent import Agent
from bilge.brain.routing import Mode, rule
from bilge.core.language import AssistantLanguage
from bilge.llm.messages import Reply
from bilge.tools.base import Registry, Risk, Tool

from .test_agent import ScriptedProvider, recorder

TR = AssistantLanguage.TURKISH


class Dictation:
    def __init__(self):
        self.active = False
        self.heard = []

    def take(self, text):
        self.heard.append(text)
        if text == "dikteyi bitir":
            self.active = False
            return "Dikte bitti."
        return ""


def agent_with(tools, rules=(), modes=(), provider=None, answers=()):
    pending = list(answers)
    asked = []

    def confirm(question):
        asked.append(question)
        return pending.pop(0)

    agent = Agent(provider or ScriptedProvider(), Registry(list(tools)), confirm, TR,
                  clock=lambda: datetime(2026, 10, 15, 14, 5), rules=list(rules), modes=list(modes))  # fmt: skip
    return agent, asked


def test_a_rule_runs_its_tool_without_the_model_and_speaks_the_result():
    start, runs = recorder("startDictation", result="Dikte açık.")
    agent, _ = agent_with([start], rules=[rule("startDictation", lambda c: c == "dikte modunu başlat")])
    assert agent.handle("dikte modunu başlat").text == "Dikte açık."
    assert runs == [{}]


def test_a_declined_rule_step_is_answered_without_the_model():
    tool, runs = recorder("spreadsheet", risk=Risk.CONFIRM, confirmation=lambda a: "C5 dolu. Üzerine yazayım mı?")
    agent, asked = agent_with(
        [tool], rules=[rule("spreadsheet", lambda c: "C5" in c, lambda c: {"command": c})], answers=[False]
    )
    assert agent.handle("C5'e 1250 yaz").text == "Tamam, yapmıyorum."
    assert runs == [] and asked == ["C5 dolu. Üzerine yazayım mı?"]


def test_rules_see_the_words_as_said():
    seen = []
    tool, _ = recorder("spreadsheet")
    agent, _ = agent_with([tool], rules=[lambda c: seen.append(c)], provider=ScriptedProvider(Reply("tamam")))
    agent.handle("on iki yaz")
    assert seen == ["on iki yaz"]


def test_a_mode_takes_input_keeps_the_conversation_open_and_ends_with_it():
    dictation = Dictation()
    mode = Mode(lambda: dictation.active, lambda: 60, lambda _: True, lambda: setattr(dictation, "active", False),
                takes=dictation.take, owns=lambda c: c == "dikteyi bitir")  # fmt: skip
    agent, _ = agent_with([], modes=[mode])
    assert agent.work_session is None
    dictation.active = True
    session = agent.work_session
    assert session.window == 60 and session.accepts("ne olursa")
    assert agent.handle_work_input("merhaba dünya").text == ""
    # Said with the wake word, a dictation control still goes to dictation, not the model.
    assert agent.handle("dikteyi bitir").text == "Dikte bitti."
    assert dictation.heard == ["merhaba dünya", "dikteyi bitir"]
    dictation.active = True
    agent.forget_conversation()
    assert not dictation.active


def test_a_mode_without_its_own_input_handling_passes_input_on():
    calls = []
    mode = Mode(lambda: True, lambda: 45, lambda _: True, lambda: None)
    tool, _ = recorder("spreadsheet", result="D3: 5.")
    agent, _ = agent_with([tool], rules=[lambda c: calls.append(c) or None], modes=[mode],
                          provider=ScriptedProvider(Reply("tamam")))  # fmt: skip
    agent.handle_work_input("D3'e topla")
    assert calls == ["D3'e topla"]


@pytest.mark.parametrize(
    ("command", "tool", "arguments"),
    [
        ("sesi yüzde 40 yap", "setVolume", {"action": "set", "level": 40}),
        ("sesi kapat", "setVolume", {"action": "mute"}),
        ("müziği durdur", "controlMusic", {"action": "pause"}),
        ("sonraki şarkı", "controlMusic", {"action": "next"}),
        ("ekranı kilitle", "systemAction", {"action": "lockScreen"}),
        ("yarın takvimde ne var", "readCalendar", {"range": "tomorrow"}),
        ("10 dakikalık zamanlayıcı kur", "setTimer", {"minutes": 10, "seconds": 0}),
        ("indirilenler klasörünü aç", "files", {"action": "openFolder", "folder": "downloads"}),
        ("firefox'u aç", "openApp", {"appName": "firefox'u"}),
        ("ekran görüntüsü al", "takeScreenshot", {"area": "wholeScreen", "toClipboard": False}),
        ("wifi'ı kapat", "setWiFi", {"power": "off"}),
    ],
)
def test_everyday_turkish_commands_map_to_tools(command, tool, arguments):
    call = fast_path.call_for(command, TR)
    assert call is not None, command
    assert (call.name, call.arguments) == (tool, arguments)


def test_english_always_goes_to_the_model():
    assert fast_path.call_for("mute the sound", AssistantLanguage.ENGLISH) is None


def test_quick_tool_missing_from_this_platform_goes_to_the_model():
    provider = ScriptedProvider(Reply("Bunu burada yapamıyorum."))
    agent, _ = agent_with([Tool("currentDateTime", "", run=lambda _: "x")], provider=provider)
    assert agent.handle("ekranı kilitle").text == "Bunu burada yapamıyorum."
