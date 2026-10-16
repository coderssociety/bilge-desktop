# Builds whisper.cpp's server with Vulkan into build\whisper, for Whisper on AMD, Intel and NVIDIA cards alike.
# Needs Visual Studio's C++ tools, Git, CMake and the Vulkan SDK (VULKAN_SDK set); the Vulkan loader (vulkan-1.dll)
# comes with every current graphics driver.
#   powershell -File packaging\whisper\build-windows.ps1
$ErrorActionPreference = "Stop"

# A reviewed release, checked by its commit as well, since a tag can be moved.
$tag = "v1.9.5"
$commit = "d1be6fde11ac6e0407606b4e42fe72d34add8037"
$work = "build\whisper-src"

Remove-Item -Recurse -Force $work, build\whisper -ErrorAction SilentlyContinue
git -c advice.detachedHead=false clone --quiet --depth 1 --branch $tag https://github.com/ggml-org/whisper.cpp $work
if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
$found = git -C $work rev-parse HEAD
if ($found -ne $commit) { throw "whisper.cpp $tag is $found, not $commit" }

# Static, with the C runtime inside, so the one program is all that ships and no Visual C++ redistributable is
# needed (whisper.cpp asks for CMake 3.5, which predates the runtime setting, hence the policy); GGML_NATIVE off, so
# it runs on processors other than the build machine's.
cmake -S $work -B "$work\build" -A x64 -DBUILD_SHARED_LIBS=OFF -DCMAKE_POLICY_DEFAULT_CMP0091=NEW `
    -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded `
    -DGGML_VULKAN=ON -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DWHISPER_BUILD_SERVER=ON -DWHISPER_BUILD_EXAMPLES=ON `
    -DWHISPER_BUILD_TESTS=OFF -DWHISPER_SDL2=OFF -DWHISPER_CURL=OFF -DWHISPER_BUILD_IS_DEV=OFF
if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }
cmake --build "$work\build" --config Release --target whisper-server --parallel
if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }

New-Item -ItemType Directory -Force build\whisper | Out-Null
Copy-Item "$work\build\bin\Release\whisper-server.exe" build\whisper\
Copy-Item "$work\LICENSE" build\whisper\LICENSE-whisper.cpp
Get-Item build\whisper\whisper-server.exe
