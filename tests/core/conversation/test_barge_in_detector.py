import pytest

from bilge.core.conversation.barge_in_detector import BargeInDetector, Command, NoBargeIn, Stop
from bilge.core.wake.wake_phrase_matcher import WakePhraseMatcher

detector = BargeInDetector(WakePhraseMatcher("Bilge"))
REPLY = "İstanbul, Boğaz'ın iki yakasına kurulmuş, binlerce yıllık tarihi olan bir şehirdir. Müzik durduruldu."


@pytest.mark.parametrize(
    "heard",
    ["İstanbul Boğaz'ın iki yakasına kurulmuş", "binlerce yıllık tarihi olan bir şehir", "müzik durduruldu", ""],
)
def test_the_assistants_own_words_leaking_back_are_ignored(heard: str) -> None:
    assert detector.evaluate(heard, speaking=REPLY) == NoBargeIn()


@pytest.mark.parametrize(
    "heard",
    ["Bilge dur", "Bilge", "dur", "Sus!", "yeter", "tamam tamam", "Bilge, yeter artık", "İstanbul Boğaz'ın dur"],
)
def test_wake_phrase_or_a_short_stop_word_stops_the_reply(heard: str) -> None:
    assert detector.evaluate(heard, speaking=REPLY) == Stop()


def test_wake_phrase_with_a_new_request_interrupts_and_runs_it() -> None:
    assert detector.evaluate("Bilge, saat kaç", speaking=REPLY) == Command("saat kaç")
    assert detector.evaluate("yıllık tarihi Bilge sesi kıs", speaking=REPLY) == Command("sesi kıs")


def test_a_stop_word_the_assistant_itself_is_saying_is_echo_not_the_user() -> None:
    assert detector.evaluate("tamam Safari'yi açtım", speaking="Tamam, Safari'yi açtım.") == NoBargeIn()
    assert detector.evaluate("Bilge dur", speaking="Tamam, Safari'yi açtım.") == Stop()
    assert detector.evaluate("ben bilge", speaking="Ben Bilge, senin asistanınım.") == NoBargeIn()
    assert detector.evaluate("bilge dur", speaking="Ben Bilge, senin asistanınım.") == Stop()


@pytest.mark.parametrize("heard", ["evet çok güzel bir şehir anlatıyorsun", "yemek hazır mı"])
def test_ordinary_speech_without_a_stop_intent_is_not_an_interruption(heard: str) -> None:
    assert detector.evaluate(heard, speaking=REPLY) == NoBargeIn()
