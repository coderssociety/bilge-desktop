import struct

from bilge.voice import gpu, placement
from bilge.voice.gpu import Gpu, Kind


def properties(name: str, kind: int, api: tuple[int, int]) -> bytes:
    version = (api[0] << 22) | (api[1] << 12)
    head = struct.pack("<IIIIi", version, 1, 0x1002, 0x73FF, kind)
    return head + name.encode().ljust(256, b"\0") + bytes(600)


def test_reads_the_device_properties() -> None:
    found = gpu._parsed(1, properties("AMD Radeon RX 6600", 2, (1, 3)))
    assert found == Gpu(1, "AMD Radeon RX 6600", Kind.DISCRETE, (1, 3))
    assert found.is_usable


def test_software_and_old_devices_are_not_used() -> None:
    assert not gpu._parsed(0, properties("llvmpipe (LLVM 17.0.6, 256 bits)", 4, (1, 3))).is_usable
    assert not gpu._parsed(0, properties("Old card", 2, (1, 1))).is_usable
    assert gpu._parsed(0, properties("Unknown kind", 9, (1, 3))).kind is Kind.OTHER


def test_prefers_a_dedicated_card() -> None:
    cards = [Gpu(0, "Intel UHD", Kind.INTEGRATED, (1, 3)), Gpu(1, "NVIDIA RTX 4060", Kind.DISCRETE, (1, 3))]
    assert gpu.best_gpu(cards, integrated=False).name == "NVIDIA RTX 4060"
    assert gpu.best_gpu(cards, integrated=True).name == "NVIDIA RTX 4060"


def test_takes_a_built_in_card_only_when_asked() -> None:
    cards = [Gpu(0, "Intel Iris Xe", Kind.INTEGRATED, (1, 3)), Gpu(1, "llvmpipe", Kind.PROCESSOR, (1, 3))]
    assert gpu.best_gpu(cards, integrated=False) is None
    assert gpu.best_gpu(cards, integrated=True).name == "Intel Iris Xe"
    assert gpu.best_gpu([], integrated=True) is None


def test_the_probe_runs_in_a_child_and_survives_a_missing_vulkan() -> None:
    # On this machine (macOS in development, a CI runner) there may be no Vulkan at all; the answer is then empty,
    # never an error.
    assert isinstance(gpu.find_gpus(), list)


def test_the_processor_is_used_when_asked(monkeypatch) -> None:
    monkeypatch.setattr(placement, "has_cuda", lambda: (_ for _ in ()).throw(AssertionError("not asked")))
    assert placement.choose("cpu") == placement.Placement(placement.Where.PROCESSOR)


def test_cuda_comes_first(monkeypatch) -> None:
    placement.forget()
    monkeypatch.setattr(placement, "has_cuda", lambda: True)
    assert placement.choose("auto").where is placement.Where.CUDA
    placement.forget()


def test_any_card_through_vulkan(monkeypatch, tmp_path) -> None:
    placement.forget()
    monkeypatch.setattr(placement, "has_cuda", lambda: False)
    monkeypatch.setattr(placement, "server_program", lambda: tmp_path / "whisper-server")
    built_in = Gpu(0, "AMD Radeon 780M", Kind.INTEGRATED, (1, 3))
    monkeypatch.setattr(gpu, "find_gpus", lambda: [built_in])
    assert placement.choose("auto").where is placement.Where.PROCESSOR
    assert placement.choose("gpu") == placement.Placement(placement.Where.VULKAN, built_in)
    placement.forget()


def test_no_whisper_cpp_in_the_build_means_the_processor(monkeypatch) -> None:
    placement.forget()
    monkeypatch.setattr(placement, "has_cuda", lambda: False)
    monkeypatch.setattr(placement, "server_program", lambda: None)
    assert placement.choose("gpu").where is placement.Where.PROCESSOR
    placement.forget()


def test_a_probe_that_crashes_is_not_waited_for():
    import queue
    import time

    class Crashed:
        exitcode = -11

        def is_alive(self):
            return False

    started = time.monotonic()
    assert gpu._answer(queue.Queue(), Crashed()) == []
    assert time.monotonic() - started < 2
