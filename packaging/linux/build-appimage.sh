#!/bin/bash
# Inside the build container: /src is the repository (read-only), /out receives Bilge-<version>-<arch>.AppImage.
set -euo pipefail

mkdir -p /work && tar --exclude=.venv --exclude=.git --exclude=build --exclude=dist -cf - -C /src . | tar -xf - -C /work
cd /work
export UV_PYTHON=3.12 UV_PYTHON_PREFERENCE=only-managed UV_HTTP_TIMEOUT=300
uv sync --quiet --locked --extra app
version=$(uv run python -c "from importlib.metadata import version; print(version('bilge'))")
arch=$(uname -m)
uv run pyinstaller packaging/bilge.spec --noconfirm --distpath build/dist --workpath build/pyinstaller --log-level WARN

app=build/Bilge.AppDir
mkdir -p "$app"
cp -a build/dist/Bilge "$app/usr"
cp packaging/linux/bilge.desktop "$app/bilge.desktop"
cp src/bilge/app/resources/bilge.png "$app/bilge.png"
cat > "$app/AppRun" <<'RUN'
#!/bin/sh
# "Bilge.AppImage" starts the tray app; "Bilge.AppImage cli …" runs the command line.
here="$(dirname "$(readlink -f "$0")")"
if [ "$1" = "cli" ]; then
    shift
    exec "$here/usr/bilge-cli" "$@"
fi
exec "$here/usr/Bilge" "$@"
RUN
chmod +x "$app/AppRun"

tool=build/appimagetool
curl -fsSL -o "$tool" "https://github.com/AppImage/appimagetool/releases/download/1.9.0/appimagetool-${arch}.AppImage"
chmod +x "$tool"
ARCH=$arch "$tool" --appimage-extract-and-run "$app" "/out/Bilge-${version}-${arch}.AppImage"
ls -la /out
