# Builds the AppImage on the oldest system Qt 6.12 supports, so it runs there and on anything newer: glibc 2.34
# (Ubuntu 22.04) for x86_64, 2.39 (Ubuntu 24.04) for arm64.
#   docker build -t bilge-appimage packaging/linux                                  # x86_64
#   docker build -t bilge-appimage --build-arg BASE=ubuntu:24.04 packaging/linux    # arm64
#   docker run --rm -v "$PWD":/src:ro -v "$PWD/dist":/out bilge-appimage
ARG BASE=ubuntu:22.04
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl file binutils libportaudio2 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
        libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libegl1 libgl1 \
        libfontconfig1 libdbus-1-3 libglib2.0-0 desktop-file-utils \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
COPY build-appimage.sh /build-appimage.sh
CMD ["bash", "/build-appimage.sh"]
