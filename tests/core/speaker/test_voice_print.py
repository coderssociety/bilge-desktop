import json
import math

from bilge.core.speaker.voice_print import THRESHOLD_RANGE, Decision, VoicePrint, decide


def unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def require(embeddings: list[list[float]]) -> VoicePrint:
    voice_print = VoicePrint.create(embeddings)
    assert voice_print is not None
    return voice_print


def test_needs_a_few_consistent_recordings_of_the_same_length() -> None:
    assert VoicePrint.create([unit([1, 0]), unit([1, 0.1])]) is None
    assert VoicePrint.create([unit([1, 0]), unit([1, 0.1]), [1, 0, 0]]) is None
    assert VoicePrint.create([unit([1, 0]), unit([1, 0.1]), unit([1, -0.1])]) is not None


def test_scores_the_enrolled_voice_above_others() -> None:
    voice_print = require([unit([1, 0.1, 0]), unit([1, -0.1, 0]), unit([1, 0, 0.1])])
    assert voice_print.score(unit([1, 0.05, 0.02])) > 0.95
    assert voice_print.score(unit([0, 1, 0])) < 0.2
    assert voice_print.consistency > 0.95


def test_a_check_needs_enough_speech_and_a_score_over_the_threshold() -> None:
    assert decide(score=0.7, seconds=2, threshold=0.5) == Decision.ACCEPTED
    assert decide(score=0.3, seconds=2, threshold=0.5) == Decision.REJECTED
    assert decide(score=0.1, seconds=0.5, threshold=0.5) == Decision.TOO_SHORT


def test_round_trips_through_json() -> None:
    voice_print = require([unit([1, 0]), unit([1, 0.1]), unit([1, -0.1])])
    assert VoicePrint.from_dict(json.loads(json.dumps(voice_print.to_dict()))) == voice_print


def test_the_threshold_follows_how_alike_the_recordings_are_within_bounds() -> None:
    lower, upper = THRESHOLD_RANGE
    tight = require([unit([1, 0.05, 0]), unit([1, -0.05, 0]), unit([1, 0, 0.05]), unit([1, 0, -0.05])])
    assert tight.suggested_threshold == upper
    loose = require([unit([1, 0.9, 0]), unit([1, -0.9, 0]), unit([1, 0, 0.9]), unit([1, 0, -0.9])])
    assert loose.suggested_threshold < tight.suggested_threshold
    assert lower <= loose.suggested_threshold <= upper
