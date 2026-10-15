import threading
import time

import numpy as np

from bilge.core.language import AssistantLanguage
from bilge.voice.assistant import Options, Status, VoiceAssistant

SPEECH = np.zeros(16_000, dtype=np.float32)


class ScriptedRecognizer:
    def __init__(self, *texts):
        self.texts = list(texts)

    def transcribe(self, samples):
        return self.texts.pop(0) if self.texts else ""


class Device:
    sample_rate = 48_000

    def clear(self):
        pass


class SilentSpeech:
    device = Device()

    def __init__(self):
        self.said = []
        self.stopped = 0

    def speak(self, text, on_sentence=None):
        self.said.append(text)
        if on_sentence:
            on_sentence(text)
        return True

    def play(self, samples):
        pass

    def stop(self):
        self.stopped += 1


class EchoAgent:
    last_reply = None

    def __init__(self, assistant_holder=None, question=None):
        self.commands = []
        self.holder = assistant_holder
        self.question = question
        self.confirmed = None

    def handle(self, command):
        self.commands.append(command)
        if self.question:
            self.confirmed = self.holder["a"].confirm(self.question)
        return type("Outcome", (), {"text": f"Tamam: {command}"})()

    def forget_conversation(self):
        pass


def make(recognizer, agent=None, options=None, quick=None):
    """`quick` is the small wake-word model; by default it hears the same as the full one."""
    speech = SilentSpeech()
    agent = agent or EchoAgent()
    quick = quick or ScriptedRecognizer(*recognizer.texts)
    assistant = VoiceAssistant(
        recognizer, speech, agent, AssistantLanguage.TURKISH, options=options, wake_recognizer=quick
    )
    return assistant, speech, agent


def wait(condition, limit=3.0):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline and not condition():
        time.sleep(0.01)
    return condition()


def test_wake_word_and_command_in_one_breath_runs_the_command():
    assistant, speech, agent = make(ScriptedRecognizer("Bilge, saat kaç?"))
    assistant.start()
    assistant._handle_utterance(SPEECH)
    assert wait(lambda: speech.said == ["Tamam: saat kaç?"])
    assert agent.commands == ["saat kaç?"]
    assistant.stop()


def test_chatter_without_the_wake_word_is_ignored():
    assistant, speech, agent = make(ScriptedRecognizer("bugün hava çok güzel"))
    assistant.start()
    assistant._handle_utterance(SPEECH)
    time.sleep(0.2)
    assert agent.commands == [] and speech.said == []
    assistant.stop()


def test_a_spoken_no_answers_the_confirmation():
    holder = {}
    agent = EchoAgent(holder, question="Hepsini sileyim mi?")
    assistant, speech, _ = make(
        ScriptedRecognizer("Bilge, hafızanı temizle", "Hayır."),
        agent,
        quick=ScriptedRecognizer("Bilge, hafızanı temizle"),
    )
    holder["a"] = assistant
    assistant.start()
    assistant._handle_utterance(SPEECH)
    assert wait(lambda: assistant.status is Status.CONFIRMING)
    assistant._handle_utterance(SPEECH)
    assert wait(lambda: agent.confirmed is False)
    assert speech.said[0] == "Hepsini sileyim mi?"
    assistant.stop()


def test_saying_stop_while_bilge_talks_cuts_it_off_without_a_follow_up():
    assistant, speech, _ = make(ScriptedRecognizer("Bilge, dur.", "Bilge, dur."))
    assistant._speaking = True
    assistant._reply_so_far = "İstanbul çok eski bir şehir"
    assistant._evaluate_barge_in(SPEECH)
    assert speech.stopped == 1
    assert assistant._stopped_by_user


def test_a_quick_misheard_stop_is_decided_by_the_full_model():
    assistant, speech, _ = make(ScriptedRecognizer("Bilge, dur."), quick=ScriptedRecognizer("Bilge tur"))
    assistant._speaking = True
    assistant._evaluate_barge_in(SPEECH)
    assert assistant._stopped_by_user and assistant._barge_command is None


def test_a_new_request_while_talking_runs_after_the_reply():
    assistant, speech, agent = make(ScriptedRecognizer("Bilge, saat kaç?"))
    assistant._speaking = True
    assistant._reply_so_far = "Ankara başkenttir"
    assistant._evaluate_barge_in(SPEECH)
    assert assistant._barge_command == "saat kaç?"


def test_barge_in_can_be_turned_off():
    assistant, _, _ = make(ScriptedRecognizer(), options=Options(barge_in=False))
    assistant._suspended = assistant._speaking = True
    for _ in range(100):
        assistant.on_chunk(np.full(512, 0.5, dtype=np.float32))
    assert assistant._barge_utterances == []


def test_stop_ends_the_background_threads():
    assistant, _, _ = make(ScriptedRecognizer())
    assistant.start()
    before = threading.active_count()
    assistant.stop()
    assert wait(lambda: threading.active_count() < before, limit=2.0)


def test_a_wake_word_the_full_model_spells_differently_still_counts():
    assistant, speech, agent = make(
        ScriptedRecognizer("Bilgé, clear your whole memory."),
        quick=ScriptedRecognizer("Bilge, clear your whole memory."),
    )
    assistant.start()
    assistant._handle_utterance(SPEECH)
    assert wait(lambda: agent.commands == ["clear your whole memory."])
    assistant.stop()


def test_a_name_the_quick_model_mangles_still_reaches_the_full_model():
    assistant, speech, _ = make(ScriptedRecognizer("Bilge, stop."), quick=ScriptedRecognizer("Bilgetler."))
    assistant._speaking = True
    assistant._evaluate_barge_in(SPEECH)
    assert assistant._stopped_by_user


def test_unrelated_speech_over_the_reply_is_not_sent_to_the_full_model():
    full = ScriptedRecognizer("Bilge, dur.")
    assistant, speech, _ = make(full, quick=ScriptedRecognizer("Bismillahirrahmanirrahim."))
    assistant._speaking = True
    assistant._evaluate_barge_in(SPEECH)
    assert full.texts == ["Bilge, dur."] and speech.stopped == 0


def test_stopping_while_bilge_thinks_drops_the_answer():
    holder = {}

    class SlowAgent(EchoAgent):
        def handle(self, command):
            holder["a"]._evaluate_barge_in(SPEECH)
            return super().handle(command)

    assistant, speech, _ = make(
        ScriptedRecognizer("Bilge, İstanbul'u anlat", "Bilge, dur."),
        SlowAgent(),
        quick=ScriptedRecognizer("Bilge, İstanbul'u anlat", "Bilge dur"),
    )
    holder["a"] = assistant
    assistant.start()
    assistant._handle_utterance(SPEECH)
    assert wait(lambda: assistant.status is not Status.THINKING and speech.stopped == 1)
    time.sleep(0.2)
    assert speech.said == []
    assistant.stop()


def test_an_english_cut_in_with_a_misspelled_name_still_counts():
    speech = SilentSpeech()
    assistant = VoiceAssistant(ScriptedRecognizer("Bilgay, what time is it?"), speech, EchoAgent(), AssistantLanguage.ENGLISH,
                               wake_recognizer=ScriptedRecognizer("Bilge"))  # fmt: skip
    assistant._speaking = True
    assistant._reply_so_far = "London began as Londinium"
    assistant._evaluate_barge_in(SPEECH)
    assert assistant._barge_command == "what time is it?"
