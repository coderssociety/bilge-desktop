"""Output volume through whichever sound server tool is installed: PipeWire's wpctl, PulseAudio's pactl, or
ALSA's amixer."""

import re

from bilge.desktop.base import VolumeState
from bilge.desktop.process import DesktopError, MissingProgram, Runner

_WPCTL_VOLUME = re.compile(r"Volume:\s*([0-9.]+)")
_PERCENT = re.compile(r"(\d+)%")
_SINK = "@DEFAULT_AUDIO_SINK@"
_PULSE_SINK = "@DEFAULT_SINK@"


class LinuxVolume:
    def __init__(self, runner: Runner):
        self._runner = runner

    def _backend(self) -> str:
        for program in ("wpctl", "pactl", "amixer"):
            if self._runner.has(program):
                return program
        raise MissingProgram("wpctl", "pactl", "amixer")

    def state(self) -> VolumeState:
        backend = self._backend()
        if backend == "wpctl":
            output = self._runner.check(["wpctl", "get-volume", _SINK])
            found = _WPCTL_VOLUME.search(output)
            if not found:
                raise DesktopError(f"Unexpected wpctl output: {output!r}")
            return VolumeState(round(float(found.group(1)) * 100), "[MUTED]" in output)
        if backend == "pactl":
            volume = self._runner.check(["pactl", "get-sink-volume", _PULSE_SINK])
            mute = self._runner.check(["pactl", "get-sink-mute", _PULSE_SINK])
            return VolumeState(_first_percent(volume), "yes" in mute.lower())
        output = self._runner.check(["amixer", "sget", "Master"])
        return VolumeState(_first_percent(output), "[off]" in output)

    def set_level(self, level: int) -> None:
        level = max(0, min(100, level))
        backend = self._backend()
        if backend == "wpctl":
            self._runner.check(["wpctl", "set-mute", _SINK, "0"])
            # -l 1.0 keeps "louder" from pushing the volume past 100%, which distorts.
            self._runner.check(["wpctl", "set-volume", "-l", "1.0", _SINK, f"{level}%"])
        elif backend == "pactl":
            self._runner.check(["pactl", "set-sink-mute", _PULSE_SINK, "0"])
            self._runner.check(["pactl", "set-sink-volume", _PULSE_SINK, f"{level}%"])
        else:
            self._runner.check(["amixer", "-q", "sset", "Master", f"{level}%", "unmute"])

    def set_muted(self, muted: bool) -> None:
        backend = self._backend()
        if backend == "wpctl":
            self._runner.check(["wpctl", "set-mute", _SINK, "1" if muted else "0"])
        elif backend == "pactl":
            self._runner.check(["pactl", "set-sink-mute", _PULSE_SINK, "1" if muted else "0"])
        else:
            self._runner.check(["amixer", "-q", "sset", "Master", "mute" if muted else "unmute"])


def _first_percent(output: str) -> int:
    found = _PERCENT.search(output)
    if not found:
        raise DesktopError(f"No volume in: {output[:200]!r}")
    return int(found.group(1))
