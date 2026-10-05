#!/usr/bin/env bash
# Builds the packages of one platform. Meant to run inside the build image (dev_scripts/package.sh
# starts it there), with the repository at /work.
#   linux    J2JME-<version>-<sha>-linux-x86_64.AppImage
#   windows  J2JME-<version>-<sha>-windows-x64-setup.exe (NSIS: for the user or for every user)
#            J2JME-<version>-<sha>-windows-x64-portable.zip
#   macos    J2JME-<version>-<sha>-macos-arm64.dmg
# Environment: J2JME_GIT_SHA (the commit id in the window title; else read from git),
#   macos: J2JME_MACOS_SDK (MacOSX*.sdk.tar.xz), MACOS_CERT_P12_BASE64 + MACOS_CERT_PASSWORD (else ad-hoc).
set -euo pipefail

target="${1:?usage: build.sh linux|windows|macos}"
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
tauri_dir="$root/desktop/src-tauri"
out="$root/dist/packages"
mkdir -p "$out"

version="$(sed -n 's/^version = "\(.*\)"/\1/p' "$tauri_dir/Cargo.toml" | head -1)"
export J2JME_GIT_SHA="${J2JME_GIT_SHA:-$(git -c safe.directory='*' rev-parse --short HEAD 2>/dev/null || echo unknown)}"
name="J2JME-${version}-${J2JME_GIT_SHA}"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$root/build/pkg-cache/target}"
echo "== $name ($target)"

"$root/packaging/stage.sh" "$target"
[ -d "$root/desktop/ui/node_modules" ] || npm ci --prefix "$root/desktop/ui"

bundle() { # a Tauri build; the frontend is built by its beforeBuildCommand
  # what an earlier bundle left (an AppDir with files that are no longer staged) is not reused
  rm -rf "$CARGO_TARGET_DIR"/release/bundle "$CARGO_TARGET_DIR"/*/release/bundle
  (cd "$tauri_dir" && tauri build --config tauri.release.conf.json "$@")
}

linux() {
  bundle --bundles appimage
  cp "$CARGO_TARGET_DIR"/release/bundle/appimage/*.AppImage "$out/$name-linux-x86_64.AppImage"
}

windows() {
  local triple=x86_64-pc-windows-msvc
  bundle --runner cargo-xwin --target "$triple" --bundles nsis
  cp "$CARGO_TARGET_DIR/$triple"/release/bundle/nsis/*-setup.exe "$out/$name-windows-x64-setup.exe"
  # portable: the executable with the same three folders beside it, which is where the application looks
  local dir="$out/$name-windows-x64-portable"
  rm -rf "$dir"; mkdir -p "$dir"
  cp "$CARGO_TARGET_DIR/$triple/release/j2jme-desktop.exe" "$dir/J2JME.exe"
  cp -a "$tauri_dir"/stage/{engine,python-runtime,tour-project} "$dir/"
  (cd "$out" && rm -f "$name-windows-x64-portable.zip" && zip -qr "$name-windows-x64-portable.zip" "$(basename "$dir")")
  rm -rf "$dir"
}

macos() {
  local triple=aarch64-apple-darwin
  : "${J2JME_MACOS_SDK:?set J2JME_MACOS_SDK to a MacOSX*.sdk.tar.xz (extracted from Xcode)}"
  local work="$root/build/pkg-cache/macos"
  rm -rf "$work"; mkdir -p "$work/sdk"
  tar -xf "$J2JME_MACOS_SDK" -C "$work/sdk" --strip-components=1
  export SDKROOT="$work/sdk"

  npm --prefix "$root/desktop/ui" run build
  (cd "$tauri_dir" && cargo zigbuild --release --target "$triple" --features tauri/custom-protocol)

  # the .app by hand: Tauri's bundler needs macOS for this
  local app="$work/J2JME Desktop.app"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cp "$CARGO_TARGET_DIR/$triple/release/j2jme-desktop" "$app/Contents/MacOS/J2JME"
  cp "$tauri_dir/icons/icon.icns" "$app/Contents/Resources/icon.icns"
  cp -a "$tauri_dir"/stage/{engine,python-runtime,tour-project} "$app/Contents/Resources/"
  cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>J2JME Desktop</string>
  <key>CFBundleDisplayName</key><string>J2JME Desktop</string>
  <key>CFBundleIdentifier</key><string>dev.j2jme.desktop</string>
  <key>CFBundleExecutable</key><string>J2JME</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${version}</string>
  <key>CFBundleVersion</key><string>${version}</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

  # sign from the inside out: every Mach-O (the interpreter, the extension modules), then the bundle
  local key=()
  if [ -n "${MACOS_CERT_P12_BASE64:-}" ]; then
    echo "$MACOS_CERT_P12_BASE64" | base64 -d > "$work/cert.p12"
    key=(--p12-file "$work/cert.p12" --p12-password "${MACOS_CERT_PASSWORD:-}")
  else
    echo "no certificate given: ad-hoc signature"
  fi
  while IFS= read -r -d '' f; do
    file -b "$f" | grep -q 'Mach-O' && rcodesign sign "${key[@]}" "$f" >/dev/null
  done < <(find "$app/Contents/Resources" -type f -print0)
  rcodesign sign "${key[@]}" "$app"
  rm -f "$work/cert.p12"

  # the dmg: an ISO of the volume's content, converted by libdmg-hfsplus
  mkdir "$work/volume"
  cp -a "$app" "$work/volume/"
  ln -s /Applications "$work/volume/Applications"
  xorrisofs -D -l -V "J2JME" -no-pad -r -dir-mode 0755 -o "$work/volume.iso" "$work/volume"
  dmg dmg "$work/volume.iso" "$out/$name-macos-arm64.dmg"
  rm -rf "$work"
}

"$target"
ls -lh "$out"/"$name"-*
