# A Linux desktop without a screen, for trying the Linux tools against the real programs:
#   docker build -t bilge-linux-check scripts/linux-check
#   docker run --rm -v "$PWD":/src:ro bilge-linux-check
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates python3 python3-uno python3-tk libreoffice-calc-nogui \
        xvfb openbox xdotool xclip xsel x11-utils scrot \
        dbus dbus-x11 libglib2.0-bin dconf-service dconf-gsettings-backend gsettings-desktop-schemas \
        pulseaudio pulseaudio-utils mpv mpv-mpris dunst libnotify-bin mousepad desktop-file-utils \
        libportaudio2 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv

RUN useradd --create-home --shell /bin/bash ayse
USER ayse
WORKDIR /home/ayse
COPY --chown=ayse inside.sh /home/ayse/inside.sh
CMD ["dbus-run-session", "--", "bash", "/home/ayse/inside.sh"]
