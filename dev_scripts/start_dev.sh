#!/usr/bin/env bash
# The desktop app in dev mode: `cargo tauri dev` starts the UI dev server (Vite, with hot reload
# of the React code) and rebuilds the Rust side when it changes. The X11 backend and the DMA-BUF
# switch are for Wayland, where WebKitGTK aborts with "Error 71 (Protocol error)" otherwise.
# The Python worker (`mapper serve`) is started once: after a change to the Python code, reopen
# the project (or restart this script). Extra arguments go to `cargo tauri dev`.
set -euo pipefail
cd "$(dirname "$0")/../desktop"
export GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1
exec cargo tauri dev "$@"
