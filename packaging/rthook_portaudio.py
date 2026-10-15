# Runs first in the packaged Linux app: sounddevice looks for PortAudio with ctypes.util.find_library, which only
# searches the system, so it is pointed at the copy that ships inside the app.
import ctypes.util
import os
import sys

_bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "libportaudio.so.2")
_find = ctypes.util.find_library


def _find_library(name):
    if name == "portaudio" and os.path.exists(_bundled):
        return _bundled
    return _find(name)


ctypes.util.find_library = _find_library
