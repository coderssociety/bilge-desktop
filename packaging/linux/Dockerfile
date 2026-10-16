# Builds the AppImage, with whisper.cpp for graphics cards, on the oldest system Qt 6.12 supports, so it runs there and
# on anything newer: glibc 2.34 (Ubuntu 22.04) for x86_64, 2.39 (Ubuntu 24.04) for arm64.
#   docker build -t bilge-appimage packaging/linux                                  # x86_64
#   docker build -t bilge-appimage --build-arg BASE=ubuntu:24.04 packaging/linux    # arm64
#   docker run --rm -v "$PWD":/src:ro -v "$PWD/dist":/out bilge-appimage
ARG BASE=ubuntu:22.04
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl file binutils libportaudio2 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
        libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libegl1 libgl1 \
        libfontconfig1 libdbus-1-3 libglib2.0-0 desktop-file-utils build-essential git gnupg \
    && rm -rf /var/lib/apt/lists/*
# What whisper.cpp's Vulkan code is built with. Ubuntu 22.04's own Vulkan headers are too old for it and it has no
# glslc, so there they come from LunarG's repository, whose key is checked against the copy kept here.
COPY lunarg-signing-key-pub.asc /tmp/lunarg.asc
RUN . /etc/os-release && if [ "$VERSION_CODENAME" = jammy ]; then \
        test "$(sha256sum /tmp/lunarg.asc | cut -d' ' -f1)" = aa1c3c29673140e77f0d6a9aaeed5d9b5621e305ead51c59fae4458bbb4df92b \
        && gpg --dearmor -o /usr/share/keyrings/lunarg.gpg /tmp/lunarg.asc \
        && echo "deb [signed-by=/usr/share/keyrings/lunarg.gpg] https://packages.lunarg.com/vulkan jammy main" \
            > /etc/apt/sources.list.d/lunarg-vulkan.list \
        && apt-get update && apt-get install -y --no-install-recommends libvulkan-dev=1.4.313.0~rc1-1lunarg22.04-1 \
            vulkan-headers=1.4.313.0~rc1-1lunarg22.04-1 shaderc=2025.2~rc1-1lunarg22.04-1 \
            spirv-headers=1.6.1+1.4.313.0~rc1-1lunarg22.04-1; \
    else \
        apt-get update && apt-get install -y --no-install-recommends libvulkan-dev glslc spirv-headers; \
    fi && rm -rf /var/lib/apt/lists/* /tmp/lunarg.asc && glslc --version
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
COPY build-appimage.sh /build-appimage.sh
CMD ["bash", "/build-appimage.sh"]
