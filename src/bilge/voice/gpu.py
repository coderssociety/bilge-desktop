"""Which graphics cards Vulkan can reach. Whisper runs on any of them through whisper.cpp (AMD, Intel and NVIDIA
alike), where faster-whisper only reaches NVIDIA cards.

The cards are asked about in a child process: a broken graphics driver may crash whatever loads it, and that must not
be Bilge.
"""

import ctypes
import logging
import multiprocessing
import queue
import sys
import time
from dataclasses import dataclass
from enum import IntEnum

log = logging.getLogger(__name__)

PROBE_SECONDS = 20
POLL_SECONDS = 0.2
_LIBRARY = {"win32": "vulkan-1.dll", "linux": "libvulkan.so.1"}
# ggml's Vulkan code needs Vulkan 1.2.
MIN_API = (1, 2)
# VkPhysicalDeviceProperties is 824 bytes on 64-bit systems; the buffer leaves room for any padding.
_PROPERTIES_BYTES = 4096
_NAME_OFFSET = 20
_NAME_BYTES = 256
_STRUCTURE_APPLICATION_INFO = 0
_STRUCTURE_INSTANCE_CREATE_INFO = 1
_SUCCESS = 0
_INCOMPLETE = 5


class Kind(IntEnum):
    OTHER = 0
    INTEGRATED = 1
    DISCRETE = 2
    VIRTUAL = 3
    PROCESSOR = 4


@dataclass(frozen=True)
class Gpu:
    # The position in Vulkan's list, which is what GGML_VK_VISIBLE_DEVICES takes.
    index: int
    name: str
    kind: Kind
    api: tuple[int, int]

    @property
    def is_usable(self) -> bool:
        """Software renderers (llvmpipe, SwiftShader) are slower than Whisper on the processor itself."""
        return self.kind in (Kind.INTEGRATED, Kind.DISCRETE, Kind.VIRTUAL) and self.api >= MIN_API


class _ApplicationInfo(ctypes.Structure):
    _fields_ = [("sType", ctypes.c_int32), ("pNext", ctypes.c_void_p), ("pApplicationName", ctypes.c_char_p),
                ("applicationVersion", ctypes.c_uint32), ("pEngineName", ctypes.c_char_p),
                ("engineVersion", ctypes.c_uint32), ("apiVersion", ctypes.c_uint32)]  # fmt: skip


class _InstanceCreateInfo(ctypes.Structure):
    _fields_ = [("sType", ctypes.c_int32), ("pNext", ctypes.c_void_p), ("flags", ctypes.c_uint32),
                ("pApplicationInfo", ctypes.POINTER(_ApplicationInfo)), ("enabledLayerCount", ctypes.c_uint32),
                ("ppEnabledLayerNames", ctypes.c_void_p), ("enabledExtensionCount", ctypes.c_uint32),
                ("ppEnabledExtensionNames", ctypes.c_void_p)]  # fmt: skip


def _version(major: int, minor: int) -> int:
    return (major << 22) | (minor << 12)


def _parsed(index: int, properties: bytes) -> Gpu:
    api = int.from_bytes(properties[0:4], "little")
    kind = int.from_bytes(properties[16:20], "little")
    raw_name = properties[_NAME_OFFSET : _NAME_OFFSET + _NAME_BYTES].split(b"\0", 1)[0]
    return Gpu(
        index=index,
        name=raw_name.decode("utf-8", errors="replace").strip(),
        kind=Kind(kind) if kind in Kind._value2member_map_ else Kind.OTHER,
        api=((api >> 22) & 0x7F, (api >> 12) & 0x3FF),
    )


def _enumerate() -> list[Gpu]:
    """In this process: loads the Vulkan loader and lists the physical devices."""
    name = _LIBRARY.get(sys.platform)
    if name is None:
        return []
    try:
        vulkan = ctypes.CDLL(name)
    except OSError:
        return []
    application = _ApplicationInfo(_STRUCTURE_APPLICATION_INFO, None, b"Bilge", 1, b"Bilge", 1, _version(1, 2))
    create = _InstanceCreateInfo(_STRUCTURE_INSTANCE_CREATE_INFO, None, 0, ctypes.pointer(application), 0, None, 0,
                                 None)  # fmt: skip
    instance = ctypes.c_void_p()
    vulkan.vkCreateInstance.argtypes = [ctypes.POINTER(_InstanceCreateInfo), ctypes.c_void_p,
                                        ctypes.POINTER(ctypes.c_void_p)]  # fmt: skip
    if vulkan.vkCreateInstance(ctypes.byref(create), None, ctypes.byref(instance)) != _SUCCESS:
        return []
    try:
        vulkan.vkEnumeratePhysicalDevices.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
                                                      ctypes.c_void_p]  # fmt: skip
        count = ctypes.c_uint32(0)
        if vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None) != _SUCCESS or count.value == 0:
            return []
        devices = (ctypes.c_void_p * count.value)()
        if vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), devices) not in (_SUCCESS, _INCOMPLETE):
            return []
        vulkan.vkGetPhysicalDeviceProperties.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        vulkan.vkGetPhysicalDeviceProperties.restype = None
        found = []
        for index in range(count.value):
            properties = ctypes.create_string_buffer(_PROPERTIES_BYTES)
            vulkan.vkGetPhysicalDeviceProperties(devices[index], properties)
            found.append(_parsed(index, properties.raw))
        return found
    finally:
        vulkan.vkDestroyInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        vulkan.vkDestroyInstance.restype = None
        vulkan.vkDestroyInstance(instance, None)


def _probe(answers) -> None:
    try:
        answers.put([(gpu.index, gpu.name, int(gpu.kind), gpu.api) for gpu in _enumerate()])
    except Exception as error:  # noqa: BLE001 - reported to the parent, which carries on without a card
        answers.put(f"{type(error).__name__}: {error}")


def find_gpus() -> list[Gpu]:
    """The cards Vulkan sees, asked in a child process; none when Vulkan is missing, broken or slow to answer."""
    if sys.platform not in _LIBRARY:
        return []
    context = multiprocessing.get_context("spawn")
    answers = context.Queue()
    child = context.Process(target=_probe, args=(answers,), name="bilge-gpu-probe", daemon=True)
    child.start()
    try:
        answer = _answer(answers, child)
    finally:
        child.join(timeout=2)
        if child.is_alive():
            child.kill()
    if isinstance(answer, str):
        log.info("Could not ask Vulkan about the graphics cards: %s", answer)
        return []
    return [Gpu(index, name, Kind(kind), tuple(api)) for index, name, kind, api in answer]


def _answer(answers, child) -> list | str:
    """Waits for the child's answer, but not past its end: a driver that crashes it answers nothing."""
    deadline = time.monotonic() + PROBE_SECONDS
    while time.monotonic() < deadline:
        try:
            return answers.get(timeout=POLL_SECONDS)
        except queue.Empty:
            if not child.is_alive():
                # It may have answered just before ending.
                try:
                    return answers.get(timeout=POLL_SECONDS)
                except queue.Empty:
                    break
    log.info("No answer about the graphics cards (exit code %s)", child.exitcode)
    return []


def best_gpu(gpus: list[Gpu], integrated: bool) -> Gpu | None:
    """A dedicated card first. `integrated`: whether a card built into the processor will do as well; on its own it
    is often no faster than the processor's cores, so it is only taken when asked for."""
    usable = [gpu for gpu in gpus if gpu.is_usable]
    ranked = sorted(usable, key=lambda gpu: (gpu.kind is not Kind.DISCRETE, gpu.index))
    if not integrated:
        ranked = [gpu for gpu in ranked if gpu.kind is Kind.DISCRETE]
    return ranked[0] if ranked else None
