#!/usr/bin/env bash
# Builds the packages of one platform. Meant to run inside the build image (dev_scripts/package.sh
# starts it there), with the repository at /work.
#   linux    J2JME-<version>-<sha>-linux-x86_64.AppImage
#            j2jme-cli-linux-x86_64.tar.gz (+ .sha256): `mapper` alone, no desktop, for CI;
#            install-mapper.sh: fetches it by the version a project's manifest.json names
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

# What the Windows installer shows: the version and the commit in its title and welcome page (the
# product name, which the install folder and the registry are keyed on, stays without them).
case "$version$J2JME_GIT_SHA" in *[!0-9A-Za-z.+-]*) echo "not a version or a commit: $version $J2JME_GIT_SHA" >&2; exit 1 ;; esac
cat > "$tauri_dir/stage/installer-hooks.nsh" <<NSH
Caption "J2JME Desktop ${version} (${J2JME_GIT_SHA}) Setup"
!define MUI_WELCOMEPAGE_TITLE "J2JME Desktop ${version} (${J2JME_GIT_SHA})"
!macro NSIS_HOOK_POSTINSTALL
  WriteRegStr SHCTX "\${UNINSTKEY}" "Comments" "Build ${J2JME_GIT_SHA}"
!macroend
NSH
[ -d "$root/desktop/ui/node_modules" ] || npm ci --prefix "$root/desktop/ui"

bundle() { # a Tauri build; the frontend is built by its beforeBuildCommand
  # what an earlier bundle left (an AppDir with files that are no longer staged) is not reused
  rm -rf "$CARGO_TARGET_DIR"/release/bundle "$CARGO_TARGET_DIR"/*/release/bundle
  (cd "$tauri_dir" && tauri build --config tauri.release.conf.json "$@")
}

linux() {
  bundle --bundles appimage
  cp "$CARGO_TARGET_DIR"/release/bundle/appimage/*.AppImage "$out/$name-linux-x86_64.AppImage"
  cli_tarball
}

# `mapper` without the desktop: the interpreter and the engine staged for the AppImage, and a
# launcher. The name has no version and no commit: packaging/install-mapper.sh builds the download
# address from the version alone (`releases/download/v<version>/j2jme-cli-linux-x86_64.tar.gz`).
cli_tarball() {
  local work="$root/build/pkg-cache/cli" archive=j2jme-cli-linux-x86_64.tar.gz
  rm -rf "$work"; mkdir -p "$work/bin"
  cp -a "$tauri_dir"/stage/{engine,python-runtime} "$work/"
  cat > "$work/bin/mapper" <<'LAUNCHER'
#!/bin/sh
# `mapper` of this unpacked archive: the bundled interpreter, the bundled engine.
here="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
PYTHONPATH="$here/engine${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
  exec "$here/python-runtime/bin/python3" -m cli.main "$@"
LAUNCHER
  chmod +x "$work/bin/mapper"
  tar -C "$work" --owner=0 --group=0 --numeric-owner --sort=name -czf "$out/$archive" bin engine python-runtime
  (cd "$out" && sha256sum "$archive" > "$archive.sha256")
  cp "$root/packaging/install-mapper.sh" "$out/install-mapper.sh"
  rm -rf "$work"
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
