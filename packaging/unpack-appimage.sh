#!/bin/sh
# unpack-appimage <file.AppImage> <dir>: unpacks an AppImage without running it (its squashfs starts
# where the runtime's ELF ends) and turns the file into a script that runs <dir>/AppRun.
set -eu
file="$1"; dir="$2"
shoff=$(readelf -h "$file" | awk '/Start of section headers/ {print $5}')
shentsize=$(readelf -h "$file" | awk '/Size of section headers/ {print $5}')
shnum=$(readelf -h "$file" | awk '/Number of section headers/ {print $5}')
unsquashfs -q -f -o $((shoff + shentsize * shnum)) -d "$dir" "$file" >/dev/null
# (Tauri passes --appimage-extract-and-run, an option of the AppImage runtime, not of the tool)
printf '#!/bin/sh\n[ "${1:-}" = --appimage-extract-and-run ] && shift\nexec %s/AppRun "$@"\n' "$dir" > "$file"
chmod +x "$file"
