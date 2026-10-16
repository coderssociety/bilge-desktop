from datetime import UTC, datetime, timedelta

from bilge.core.conversation.conversation_flow import (
    AcknowledgeWake,
    AwaitingCommand,
    ConversationFlow,
    FollowUp,
    ListeningForWake,
    NoAction,
    Processing,
    Responding,
    ReturnToIdle,
    RunCommand,
    RunWorkInput,
    WorkSession,
)
from bilge.core.wake.wake_phrase_matcher import WakePhraseMatcher

START = datetime.fromtimestamp(1_000, UTC)


def later(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


def make_flow() -> ConversationFlow:
    return ConversationFlow(WakePhraseMatcher("asistan"), command_timeout=6, follow_up_window=5)


def test_ignores_speech_without_the_wake_phrase() -> None:
    flow = make_flow()
    assert flow.heard("bugün hava güzel", at=START) == NoAction()
    assert flow.phase == ListeningForWake()


def test_wake_phrase_with_a_command_runs_it_immediately() -> None:
    flow = make_flow()
    assert flow.heard("Asistan, Safari'yi aç", at=START) == RunCommand("Safari'yi aç")
    assert flow.phase == Processing()


def test_bare_wake_phrase_waits_for_the_command_then_runs_it() -> None:
    flow = make_flow()
    assert flow.heard("Asistan", at=START) == AcknowledgeWake()
    assert flow.phase == AwaitingCommand(deadline=later(6))
    assert flow.heard("saat kaç", at=later(2)) == RunCommand("saat kaç")


def test_command_wait_times_out_back_to_idle() -> None:
    flow = make_flow()
    flow.heard("asistan", at=START)
    assert flow.tick(at=later(5)) == NoAction()
    assert flow.tick(at=later(6.1)) == ReturnToIdle(timed_out=True)
    assert flow.phase == ListeningForWake()


def test_speech_that_has_started_is_not_cut_by_the_deadline() -> None:
    flow = make_flow()
    flow.heard("asistan", at=START)
    flow.speech_started(at=later(5.5))
    assert flow.tick(at=later(7)) == NoAction()
    assert flow.heard("yarın sabah yedide beni uyandır", at=later(8)) == RunCommand("yarın sabah yedide beni uyandır")


def test_cancel_words_end_the_exchange() -> None:
    flow = make_flow()
    flow.heard("asistan", at=START)
    assert flow.heard("Vazgeç.", at=later(1)) == ReturnToIdle(timed_out=False)
    assert flow.phase == ListeningForWake()


def test_speech_while_processing_or_responding_is_ignored() -> None:
    flow = make_flow()
    flow.heard("asistan saat kaç", at=START)
    assert flow.heard("asistan müziği aç", at=START) == NoAction()
    flow.response_started()
    assert flow.phase == Responding()
    assert flow.heard("asistan müziği aç", at=START) == NoAction()


def test_after_a_reply_a_follow_up_needs_no_wake_phrase_until_the_window_closes() -> None:
    flow = make_flow()
    flow.heard("asistan saat kaç", at=START)
    flow.response_started()
    flow.response_finished(at=later(2), allow_follow_up=True)
    assert flow.phase == FollowUp(deadline=later(7))
    assert flow.heard("peki yarın?", at=later(3)) == RunCommand("peki yarın?")


def test_follow_up_window_closes_silently() -> None:
    flow = make_flow()
    flow.heard("asistan saat kaç", at=START)
    flow.response_finished(at=START, allow_follow_up=True)
    assert flow.tick(at=later(6)) == ReturnToIdle(timed_out=False)


def test_a_repeated_wake_phrase_in_follow_up_is_stripped_from_the_command() -> None:
    flow = make_flow()
    flow.heard("asistan saat kaç", at=START)
    flow.response_finished(at=START, allow_follow_up=True)
    assert flow.heard("Asistan, sesi kıs", at=later(1)) == RunCommand("sesi kıs")


def test_without_follow_up_the_flow_returns_to_wake_listening() -> None:
    flow = make_flow()
    flow.heard("asistan saat kaç", at=START)
    flow.response_finished(at=START, allow_follow_up=False)
    assert flow.phase == ListeningForWake()


def test_a_work_session_keeps_listening_longer_but_only_for_what_it_accepts() -> None:
    flow = make_flow()
    flow.heard("Asistan, D3'e B2 ile B1'i topla", at=START)
    flow.response_started()
    session = WorkSession(window=40, accepts=lambda text: "topla" in text or "yaz" in text)
    flow.response_finished(at=START, allow_follow_up=False, session=session)
    assert flow.phase == FollowUp(deadline=later(40))
    # Chatter in the room is ignored and does not end the session.
    assert flow.heard("akşam ne yiyoruz", at=later(5)) == NoAction()
    assert flow.is_awaiting_speech
    assert flow.heard("C5'e 1250 yaz", at=later(8)) == RunWorkInput("C5'e 1250 yaz")


def test_in_a_work_session_the_wake_phrase_still_reaches_everything() -> None:
    flow = make_flow()
    flow.response_started()
    flow.response_finished(at=START, allow_follow_up=False, session=WorkSession(window=40, accepts=lambda _: False))
    assert flow.heard("Asistan, saat kaç", at=later(3)) == RunCommand("saat kaç")


def test_ignored_speech_in_a_work_session_does_not_keep_the_window_open_past_its_deadline() -> None:
    flow = make_flow()
    flow.response_started()
    flow.response_finished(at=START, allow_follow_up=False, session=WorkSession(window=40, accepts=lambda _: False))
    flow.speech_started(at=later(39))
    assert flow.heard("bir şeyler", at=later(41)) == NoAction()
    assert flow.tick(at=later(41)) == ReturnToIdle(timed_out=False)


def test_a_bare_wake_word_in_the_follow_up_window_starts_a_fresh_wait():
    flow = ConversationFlow(WakePhraseMatcher("Asistan"))
    flow.heard("Asistan, saat kaç", at=START)
    flow.response_started()
    flow.response_finished(at=later(2), allow_follow_up=True)
    assert flow.heard("Asistan", at=later(6)) == AcknowledgeWake()
    assert isinstance(flow.phase, AwaitingCommand)
    assert flow.tick(at=later(11)) == NoAction()
    assert flow.heard("dolar kaç lira", at=later(11)) == RunCommand("dolar kaç lira")


def test_the_shortcut_wakes_like_the_bare_wake_phrase() -> None:
    flow = make_flow()
    assert flow.shortcut_pressed(START) == AcknowledgeWake()
    assert flow.phase == AwaitingCommand(deadline=later(6))
    assert flow.heard("saat kaç", later(2)) == RunCommand("saat kaç")


def test_pressing_the_shortcut_again_while_waiting_cancels() -> None:
    flow = make_flow()
    flow.shortcut_pressed(START)
    assert flow.shortcut_pressed(later(1)) == ReturnToIdle(timed_out=False)
    assert flow.phase == ListeningForWake()


def test_the_shortcut_in_the_follow_up_window_starts_a_fresh_wait_outside_the_work_session() -> None:
    flow = make_flow()
    flow.response_started()
    flow.response_finished(at=START, allow_follow_up=True, session=WorkSession(window=30, accepts=lambda _: True))
    assert flow.shortcut_pressed(later(1)) == AcknowledgeWake()
    assert flow.heard("bir sonraki şarkı", later(2)) == RunCommand("bir sonraki şarkı")


def test_the_shortcut_changes_nothing_while_bilge_answers() -> None:
    flow = make_flow()
    flow.heard("asistan saat kaç", START)
    assert flow.shortcut_pressed(later(1)) == NoAction()
    flow.response_started()
    assert flow.shortcut_pressed(later(1)) == NoAction()
    assert flow.phase == Responding()
