#!/bin/bash
# Builds whisper.cpp's server with Vulkan into build/whisper, for Whisper on AMD, Intel and NVIDIA cards alike.
# Run inside the AppImage builder (packaging/linux/Dockerfile has the Vulkan headers, glslc and git); the Vulkan
# loader itself (libvulkan.so.1) comes from the user's system with the graphics driver.
#   bash packaging/whisper/build-linux.sh
set -euo pipefail

# A reviewed release, checked by its commit as well, since a tag can be moved.
TAG=v1.9.5
COMMIT=d1be6fde11ac6e0407606b4e42fe72d34add8037
CMAKE_VERSION=3.31.6

work=build/whisper-src
rm -rf "$work" build/whisper
git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$TAG" https://github.com/ggml-org/whisper.cpp "$work"
test "$(git -C "$work" rev-parse HEAD)" = "$COMMIT" || { echo "whisper.cpp $TAG is not $COMMIT" >&2; exit 1; }

# Vulkan's glslc component needs CMake 3.24; Ubuntu 22.04 has 3.22.
cmake=(uv tool run --quiet "cmake==$CMAKE_VERSION")
# Static, so the one program is all that ships; without OpenMP, so it needs no libgomp; GGML_NATIVE off, so it runs
# on processors other than the build machine's.
"${cmake[@]}" -S "$work" -B "$work/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_VULKAN=ON \
    -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DWHISPER_BUILD_SERVER=ON -DWHISPER_BUILD_EXAMPLES=ON \
    -DWHISPER_BUILD_TESTS=OFF -DWHISPER_SDL2=OFF -DWHISPER_CURL=OFF -DWHISPER_BUILD_IS_DEV=OFF > "$work/cmake.log"
"${cmake[@]}" --build "$work/build" --target whisper-server --parallel "$(nproc)" > "$work/build.log"

mkdir -p build/whisper
cp "$work/build/bin/whisper-server" build/whisper/
cp "$work/LICENSE" build/whisper/LICENSE-whisper.cpp
strip build/whisper/whisper-server
ldd build/whisper/whisper-server
