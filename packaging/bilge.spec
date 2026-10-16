# PyInstaller: one folder with Bilge (the tray app, no console) and bilge-cli (the command line; a different name,
# since Windows sees Bilge.exe and bilge.exe as the same file).
#   uv run pyinstaller packaging/bilge.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
windows = sys.platform == "win32"

datas = [
    (str(root / "src/bilge/app/resources"), "bilge/app/resources"),
    # Run by LibreOffice's own Python, so it ships as a file rather than inside the archive.
    (str(root / "src/bilge/desktop/calc/uno_server.py"), "bilge/desktop/calc"),
]
for package in ("faster_whisper", "certifi", "caldav", "icalendar", "livekit"):
    datas += collect_data_files(package)
# Bilge's own version, which the update check compares with the newest release.
datas += copy_metadata("bilge")
# whisper.cpp with Vulkan, built by packaging/whisper; kept as plain files, since PyInstaller has nothing to add to a
# static program. A build without it runs Whisper on the processor or an NVIDIA card only.
if (root / "build/whisper").is_dir():
    datas.append((str(root / "build/whisper"), "whisper"))
# Only on some systems: PortAudio's own copy (Windows, macOS) and the time zone database (Windows).
for package in ("_sounddevice_data", "tzdata"):
    try:
        datas += collect_data_files(package)
    except ImportError:
        pass
binaries = []
for package in ("onnxruntime", "livekit", "kaldi_native_fbank", "soxr", "ctranslate2"):
    binaries += collect_dynamic_libs(package)
if sys.platform.startswith("linux"):
    # sounddevice brings PortAudio on Windows and macOS only; on Linux it is the system's, so it is bundled here.
    import subprocess

    found = [line.split(" => ")[1] for line in subprocess.check_output(["ldconfig", "-p"], text=True).splitlines()
             if "libportaudio.so.2" in line and " => " in line]  # fmt: skip
    if not found:
        raise SystemExit("Install libportaudio2 to build")
    binaries.append((found[0], "."))

hidden = collect_submodules("bilge") + collect_submodules("keyring.backends")
if windows:
    hidden += collect_submodules("winrt") + collect_submodules("comtypes") + ["pycaw.pycaw"]
else:
    hidden += collect_submodules("jeepney")



def analyse(script: str):
    hooks = [str(root / "packaging/rthook_portaudio.py")] if sys.platform.startswith("linux") else []
    return Analysis([str(root / "packaging" / script)], pathex=[str(root / "src")], datas=datas, binaries=binaries,
                    hiddenimports=hidden, excludes=["tkinter", "pytest", "radicale", "PyInstaller"],
                    runtime_hooks=hooks)


# Each program has its own analysis (a script list also holds PyInstaller's start-up hooks); both import the same
# packages, so one set of libraries serves the two.
app_analysis, cli_analysis = analyse("launch_app.py"), analyse("launch_cli.py")
if sys.platform.startswith("linux"):
    # The system's own copies, as AppImage's exclude list names them: they must match the system's configuration
    # files and drivers. The build system's older fontconfig can't read newer configuration, its libstdc++ is older
    # than the graphics drivers need, and ALSA without its configuration stops the program inside PortAudio. Copies
    # a package renamed for itself (PyAV's libasound-<hash>) are its own and stay.
    system_libraries = {"libasound.so.2", "libcom_err.so.2", "libexpat.so.1", "libfontconfig.so.1", "libfreetype.so.6",
                        "libgcc_s.so.1", "libgpg-error.so.0", "libharfbuzz.so.0", "libmvec.so.1", "libstdc++.so.6",
                        "libuuid.so.1", "libX11.so.6", "libX11-xcb.so.1", "libz.so.1"}  # fmt: skip
    for analysed in (app_analysis, cli_analysis):
        analysed.binaries = [entry for entry in analysed.binaries if Path(entry[0]).name not in system_libraries]
icon = str(root / "build/bilge.ico") if windows else None
app = EXE(PYZ(app_analysis.pure), app_analysis.scripts, exclude_binaries=True, name="Bilge", console=False, icon=icon)
cli = EXE(PYZ(cli_analysis.pure), cli_analysis.scripts, exclude_binaries=True, name="bilge-cli", console=True, icon=icon)
COLLECT(app, cli, app_analysis.binaries, app_analysis.datas, cli_analysis.binaries, cli_analysis.datas, name="Bilge")
