from bilge.core.audio.sample_chunker import SampleChunker


def test_emits_fixed_size_chunks_and_carries_the_remainder() -> None:
    chunker = SampleChunker(chunk_size=4)
    assert chunker.append([1, 2, 3]) == []
    assert chunker.append([4, 5, 6, 7, 8, 9]) == [[1, 2, 3, 4], [5, 6, 7, 8]]
    assert chunker.pending_count == 1


def test_reset_drops_pending_samples() -> None:
    chunker = SampleChunker(chunk_size=4)
    chunker.append([1, 2])
    chunker.reset()
    assert chunker.append([3, 4, 5, 6]) == [[3, 4, 5, 6]]
