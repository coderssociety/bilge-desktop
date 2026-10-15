from bilge.core.audio.speech_segmenter import Configuration, EndReason, Segment, SpeechSegmenter

# 4 samples per chunk, so each chunk is easy to identify by its fill value.
CONFIG = Configuration(
    chunk_duration=0.25,
    start_threshold=0.6,
    end_threshold=0.35,
    min_silence=0.5,
    pre_roll=0.25,
    min_speech=0.5,
    max_segment=2.0,
)


def chunk(value: float) -> list[float]:
    return [value] * 4


def test_emits_a_segment_with_pre_roll_once_silence_lasts_long_enough() -> None:
    segmenter = SpeechSegmenter(CONFIG)
    probabilities = [0.1, 0.1, 0.9, 0.9, 0.8, 0.1, 0.1, 0.1]
    segments: list[Segment] = []
    for index, probability in enumerate(probabilities):
        segments += segmenter.process(chunk(float(index)), probability=probability)
    assert len(segments) == 1
    # pre-roll chunk 1, speech 2...4, trailing silence 5...6 that confirmed the end
    assert segments[0].samples == [sample for value in [1, 2, 3, 4, 5, 6] for sample in chunk(float(value))]
    assert segments[0].end_reason == EndReason.SILENCE


def test_drops_blips_shorter_than_the_minimum_speech_duration() -> None:
    segmenter = SpeechSegmenter(CONFIG)
    segments: list[Segment] = []
    for probability in [0.9, 0.1, 0.1, 0.1]:
        segments += segmenter.process(chunk(1), probability=probability)
    assert segments == []


def test_hysteresis_keeps_a_segment_open_through_brief_dips() -> None:
    segmenter = SpeechSegmenter(CONFIG)
    segments: list[Segment] = []
    for probability in [0.9, 0.5, 0.9, 0.4, 0.9, 0.1, 0.1]:
        segments += segmenter.process(chunk(1), probability=probability)
    assert len(segments) == 1
    assert len(segments[0].samples) == 7 * 4


def test_cuts_segments_that_exceed_the_maximum_length() -> None:
    segmenter = SpeechSegmenter(CONFIG)
    segments: list[Segment] = []
    for _ in range(9):
        segments += segmenter.process(chunk(1), probability=0.9)
    assert len(segments) == 1
    assert segments[0].end_reason == EndReason.MAX_LENGTH
    assert segmenter.is_in_speech


def test_flush_returns_an_in_progress_segment() -> None:
    segmenter = SpeechSegmenter(CONFIG)
    segmenter.process(chunk(1), probability=0.9)
    segmenter.process(chunk(2), probability=0.9)
    flushed = segmenter.flush()
    assert flushed is not None
    assert len(flushed.samples) == 8
    assert segmenter.flush() is None
