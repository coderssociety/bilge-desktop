"""Where local Whisper runs: an NVIDIA card through faster-whisper when CUDA is installed, any other card through
whisper.cpp and Vulkan, or the processor."""

import functools
import logging
from dataclasses import dataclass
from enum import StrEnum

from bilge.voice import gpu as gpus
from bilge.voice.recognizers import has_cuda
from bilge.voice.whisper_cpp import server_program

log = logging.getLogger(__name__)


class Where(StrEnum):
    PROCESSOR = "cpu"
    CUDA = "cuda"
    VULKAN = "vulkan"


@dataclass(frozen=True)
class Placement:
    where: Where
    # The card whisper.cpp uses; for CUDA, faster-whisper picks it.
    gpu: gpus.Gpu | None = None

    @property
    def description(self) -> str:
        if self.where is Where.VULKAN and self.gpu is not None:
            return self.gpu.name
        return "NVIDIA (CUDA)" if self.where is Where.CUDA else ""


def choose(accelerator: str) -> Placement:
    """`accelerator`: "cpu"; "gpu", any usable card; "auto", a dedicated card if there is one."""
    if accelerator == "cpu":
        return Placement(Where.PROCESSOR)
    return _with_card(accelerator == "gpu")


# The answer stays the same while Bilge runs, and asking takes a child process.
@functools.cache
def _with_card(integrated: bool) -> Placement:
    if has_cuda():
        return Placement(Where.CUDA)
    if server_program() is None:
        log.info("No whisper.cpp in this build; Whisper runs on the processor")
        return Placement(Where.PROCESSOR)
    found = gpus.find_gpus()
    log.info("Graphics cards: %s", ", ".join(f"{g.name} ({g.kind.name.lower()})" for g in found) or "none")
    chosen = gpus.best_gpu(found, integrated=integrated)
    return Placement(Where.VULKAN, chosen) if chosen is not None else Placement(Where.PROCESSOR)


def forget() -> None:
    """For the settings' test button: ask the cards again."""
    _with_card.cache_clear()
