#!/usr/bin/env bash
# The desktop packages, built in the packaging image (packaging/Dockerfile): everything from Linux.
# Usage: dev_scripts/package.sh linux|windows|macos [more…]      output: dist/packages/
#   macOS needs J2JME_MACOS_SDK=<path to MacOSX*.sdk.tar.xz>; with MACOS_CERT_P12_BASE64 and
#   MACOS_CERT_PASSWORD the app is signed with that certificate, otherwise ad-hoc.
# The image is built the first time (a few minutes). target/ and the downloads are kept in
# build/pkg-cache, or in the volume j2jme-pkg-cache-<target> with J2JME_PKG_COPY=1 (one per target,
# so the targets can be built at the same time on the same daemon).
# J2JME_PKG_COPY=1: for a docker daemon that does not share this machine's files (CI on dind):
# the repository is copied into the container and the packages copied out, no bind mounts.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
[ "$#" -gt 0 ] || { echo "usage: $0 linux|windows|macos [more…]" >&2; exit 2; }
image=j2jme-packager
sha="$(git rev-parse --short HEAD)"

docker build -q -t "$image" -f packaging/Dockerfile packaging >/dev/null
mkdir -p dist/packages

env_args=(
  -e HOME=/work/build/pkg-cache/home -e CARGO_HOME=/work/build/pkg-cache/cargo
  -e J2JME_PKG_CACHE=/work/build/pkg-cache -e CARGO_TARGET_DIR=/work/build/pkg-cache/target
  -e J2JME_GIT_SHA="$sha" -e MACOS_CERT_P12_BASE64 -e MACOS_CERT_PASSWORD
)
[ -z "${J2JME_MACOS_SDK:-}" ] || env_args+=(-e J2JME_MACOS_SDK=/tmp/macos-sdk.tar.xz)

for target in "$@"; do
  if [ -z "${J2JME_PKG_COPY:-}" ]; then
    mkdir -p build/pkg-cache
    mounts=(-v "$root:/work")
    [ -z "${J2JME_MACOS_SDK:-}" ] || mounts+=(-v "$(readlink -f "$J2JME_MACOS_SDK"):/tmp/macos-sdk.tar.xz:ro")
    docker run --rm --user "$(id -u):$(id -g)" -w /work "${mounts[@]}" "${env_args[@]}" \
      "$image" packaging/build.sh "$target"
  else
    volume="j2jme-pkg-cache-$target"
    docker volume create "$volume" >/dev/null
    cid="$(docker create -w /work -v "$volume:/work/build/pkg-cache" "${env_args[@]}" \
      "$image" packaging/build.sh "$target")"
    trap 'docker rm -f "$cid" >/dev/null' EXIT
    docker cp "$root/." "$cid:/work"
    [ -z "${J2JME_MACOS_SDK:-}" ] || docker cp "$J2JME_MACOS_SDK" "$cid:/tmp/macos-sdk.tar.xz"
    docker start -a "$cid"
    docker cp "$cid:/work/dist/packages/." dist/packages/
    docker rm -f "$cid" >/dev/null; trap - EXIT
  fi
done
ls -lh dist/packages
