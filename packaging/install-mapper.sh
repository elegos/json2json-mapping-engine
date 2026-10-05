#!/bin/sh
# Installs the `mapper` of the version a project was built with, and puts it in the PATH (for CI).
#
#   install-mapper.sh [--config FILE] [--version X.Y.Z] [--releases URL] [--dir DIR]
#
# The version is `engine` under [project] in the project's mapper.toml (or --version). The
# archive is taken from <releases>/v<version>/j2jme-cli-linux-x86_64.tar.gz, checked against the
# .sha256 beside it, and unpacked in <dir>/<version> (a version already there is reused).
#   --releases  the releases' download address, the same on GitHub and Forgejo:
#               https://<host>/<owner>/<repo>/releases/download      (env J2JME_RELEASES_URL)
#   --dir       where versions are kept (env J2JME_HOME, default ~/.local/share/j2jme)
#   env J2JME_TOKEN: a token for a private repository.
# Then `<dir>/<version>/bin` is added to the PATH of the next steps of a GitHub / Forgejo Actions
# job ($GITHUB_PATH); anywhere else it prints the line to put in the PATH. Needs sh, curl, tar
# and sha256sum; no Python: the archive brings its own.
set -eu

config=mapper.toml
version=
releases="${J2JME_RELEASES_URL:-}"
home="${J2JME_HOME:-${HOME:-.}/.local/share/j2jme}"
asset=j2jme-cli-linux-x86_64.tar.gz

die() { echo "install-mapper: $*" >&2; exit 1; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)   config="${2:?--config needs a file}"; shift 2 ;;
    --version)  version="${2:?--version needs a version}"; shift 2 ;;
    --releases) releases="${2:?--releases needs an address}"; shift 2 ;;
    --dir)      home="${2:?--dir needs a folder}"; shift 2 ;;
    -h|--help)  sed -n '2,/^set -eu/{/^set -eu/!p;}' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

if [ -z "$version" ]; then
  [ -f "$config" ] || die "no $config (run in the project's folder, or give --version)"
  version="$(awk '
    /^[[:space:]]*\[/ { in_project = ($0 ~ /^[[:space:]]*\[project\][[:space:]]*(#.*)?$/) }
    in_project && /^[[:space:]]*engine[[:space:]]*=/ {
      if (match($0, /"[^"]*"/)) { print substr($0, RSTART + 1, RLENGTH - 2); exit }
    }' "$config")"
  [ -n "$version" ] || die "no engine version under [project] in $config (\`mapper upgrade\` writes it)"
fi
case "$version" in
  *[!0-9A-Za-z.+-]*|"") die "not a version: $version" ;;
esac

dest="$home/$version"
if [ ! -x "$dest/bin/mapper" ]; then
  [ -n "$releases" ] || die "where are the releases? give --releases or J2JME_RELEASES_URL"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  base="${releases%/}/v$version"
  auth=
  [ -z "${J2JME_TOKEN:-}" ] || auth="Authorization: token $J2JME_TOKEN"
  fetch() { # fetch <name>
    if [ -n "$auth" ]; then curl -fsSL -H "$auth" -o "$tmp/$1" "$base/$1"; else curl -fsSL -o "$tmp/$1" "$base/$1"; fi
  }
  fetch "$asset" || die "cannot download $base/$asset (is there a release v$version?)"
  fetch "$asset.sha256" || die "cannot download $base/$asset.sha256"
  (cd "$tmp" && sha256sum -c "$asset.sha256" >/dev/null 2>&1) || die "bad checksum: $asset"
  mkdir -p "$tmp/unpacked"
  tar -xzf "$tmp/$asset" -C "$tmp/unpacked"
  [ -x "$tmp/unpacked/bin/mapper" ] || die "no bin/mapper in $asset"
  mkdir -p "$home"
  rm -rf "$dest"
  mv "$tmp/unpacked" "$dest"
fi

if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$dest/bin" >> "$GITHUB_PATH"
  echo "mapper $version installed in $dest/bin (added to the PATH of the next steps)"
else
  echo "mapper $version installed in $dest/bin"
  echo "export PATH=\"$dest/bin:\$PATH\""
fi
