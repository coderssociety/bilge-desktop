#!/bin/bash
# Runs inside the container: starts a screen, a window manager, sound, a notification service and LibreOffice,
# then the whole test suite plus the tests that need the real programs.
set -euo pipefail

export DISPLAY=:99 XDG_CURRENT_DESKTOP=GNOME XDG_RUNTIME_DIR=/tmp/runtime-ayse
mkdir -p -m 0700 "$XDG_RUNTIME_DIR"
Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 &
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.1; done
openbox >/dev/null 2>&1 &
dunst >/dev/null 2>&1 &
pulseaudio --daemonize=yes --exit-idle-time=-1 --log-target=stderr 2>/dev/null
pactl load-module module-null-sink sink_name=speakers >/dev/null
pactl set-default-sink speakers

mkdir -p work
tar --exclude=.venv --exclude=.git --exclude=.pytest_cache --exclude=__pycache__ -cf - -C /src . | tar -xf - -C work
cd work
export UV_PYTHON=3.12
uv sync --quiet
echo "== whole suite on $(. /etc/os-release && echo "$PRETTY_NAME")"
uv run pytest -q -p no:warnings
echo "== real desktop"
BILGE_REAL_DESKTOP=1 uv run pytest -q -p no:warnings tests/linux -rs
