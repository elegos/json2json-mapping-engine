#!/usr/bin/env bash
# Assembles what the application ships next to its executable, for one target platform:
#   desktop/src-tauri/stage/engine          the Python packages + their dependencies (wheels of the target)
#   desktop/src-tauri/stage/python-runtime  a relocatable CPython of the target
#   desktop/src-tauri/stage/tour-project    the project the tutorial opens a copy of
# Usage: packaging/stage.sh linux|windows|macos      (runs anywhere `uv` and `curl` do)
set -euo pipefail

target="${1:?usage: stage.sh linux|windows|macos}"
root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=versions.env
. "$root/packaging/versions.env"
cache="${J2JME_PKG_CACHE:-$root/build/pkg-cache}/downloads"
stage="$root/desktop/src-tauri/stage"

case "$target" in
  linux)   triple=x86_64-unknown-linux-gnu; platform=x86_64-manylinux_2_28; sha="$PBS_SHA256_linux" ;;
  windows) triple=x86_64-pc-windows-msvc;   platform=x86_64-pc-windows-msvc; sha="$PBS_SHA256_windows" ;;
  macos)   triple=aarch64-apple-darwin;     platform=aarch64-apple-darwin;   sha="$PBS_SHA256_macos" ;;
  *) echo "unknown target: $target" >&2; exit 2 ;;
esac

archive="cpython-${PBS_PYTHON}+${PBS_RELEASE}-${triple}-install_only_stripped.tar.gz"
mkdir -p "$cache"
if [ ! -f "$cache/$archive" ]; then
  curl -fsSL -o "$cache/$archive.part" \
    "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${archive//+/%2B}"
  mv "$cache/$archive.part" "$cache/$archive"
fi
echo "$sha  $cache/$archive" | sha256sum -c - >/dev/null || { echo "bad checksum: $archive" >&2; exit 1; }

rm -rf "$stage"
mkdir -p "$stage"

# 1. the interpreter (links dereferenced: the bundler copies files, not links)
tar -xzf "$cache/$archive" -C "$stage"
mv "$stage/python" "$stage/python-runtime"
rm -rf "$stage/python-runtime"/{include,share} \
       "$stage/python-runtime"/lib/python3.*/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3} \
       "$stage/python-runtime"/lib/{tcl*,tk*,itcl*,Tix*,libtcl*,libtk*,thread*,pkgconfig} \
       "$stage/python-runtime"/lib/python3.*/lib-dynload/_tkinter* \
       "$stage/python-runtime"/{tcl,Lib/test,Lib/idlelib,Lib/tkinter,Lib/turtledemo,Lib/ensurepip} \
       "$stage/python-runtime"/DLLs/{_tkinter.pyd,tcl*.dll,tk*.dll}
find "$stage/python-runtime" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$stage/python-runtime" -type l | while read -r link; do
  real="$(readlink -f "$link")"; rm "$link"; cp -a "$real" "$link"
done
rm -rf "$stage/python-runtime"/bin/{python,python3.14,python3.14-config,python3-config,idle3*,pip*,pydoc3*} \
       "$stage/python-runtime"/lib/libpython3.14.so \
       "$stage/python-runtime"/lib/python3.*/site-packages/{pip*,setuptools*,pkg_resources*,_distutils_hack*} \
       "$stage/python-runtime"/Lib/site-packages/{pip*,setuptools*,pkg_resources*,_distutils_hack*}
# the layout python.rs looks for
[ -x "$stage/python-runtime/bin/python3" ] || [ -f "$stage/python-runtime/python.exe" ] \
  || { echo "no interpreter in the staged runtime" >&2; exit 1; }

# 2. the engine: its own packages, then the dependencies as wheels for the target platform
engine="$stage/engine"
mkdir -p "$engine"
for pkg in cli compiler transpiler runtime; do
  cp -a "$root/$pkg" "$engine/$pkg"
done
find "$engine" -name __pycache__ -type d -prune -exec rm -rf {} +
(cd "$root" && uv export --no-dev --no-hashes --frozen --no-emit-project -o "$stage/requirements.txt" >/dev/null)
uv pip install --quiet --target "$engine" --python-platform "$platform" \
  --python-version "${PBS_PYTHON%.*}" --only-binary :all: --no-deps -r "$stage/requirements.txt"
rm -rf "$engine/bin" "$stage/requirements.txt"

# Byte-code written now, as nothing may be written next to the application later (an installation
# for all users, an AppImage, a read-only volume). `unchecked-hash`: valid wherever the files go.
uv run --no-project --python "${PBS_PYTHON%.*}" python -m compileall -q -f \
  --invalidation-mode unchecked-hash "$engine" >/dev/null

# 3. the tutorial project
cp -a "$root/desktop/fixtures/tour-project" "$stage/tour-project"

echo "staged for $target: $(du -sh "$stage" | cut -f1) in $stage"
