from bilge.brain.policy import Action, Verdict, decide
from bilge.tools.base import Risk


def test_safe_tools_run_and_risky_ones_ask():
    assert decide("setVolume", Risk.SAFE, read_untrusted=False) == Verdict(Action.RUN)
    assert decide("sendMessage", Risk.CONFIRM, read_untrusted=False) == Verdict(Action.CONFIRM)
    assert decide("runCommand", Risk.DISABLED, read_untrusted=False) == Verdict(Action.REFUSE)


def test_after_untrusted_content_exfiltrating_tools_are_refused():
    for name in ["readWebPage", "openWebsite", "searchWeb", "typeText", "remember"]:
        assert decide(name, Risk.SAFE, read_untrusted=True).action is Action.REFUSE


def test_after_untrusted_content_side_effects_need_a_yes():
    assert decide("setVolume", Risk.SAFE, read_untrusted=True) == Verdict(Action.CONFIRM, cautioned=True)
    assert decide("sendMessage", Risk.CONFIRM, read_untrusted=True) == Verdict(Action.CONFIRM, cautioned=True)


def test_after_untrusted_content_reading_stays_free():
    assert decide("weather", Risk.SAFE, read_untrusted=True) == Verdict(Action.RUN)
