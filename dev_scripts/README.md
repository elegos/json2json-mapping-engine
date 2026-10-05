# dev_scripts

Scripts the development reuses; add one here when a command sequence is run more than once.

| Script | What it does |
|---|---|
| `check.sh` | what CI runs offline: ruff, basedpyright (local config moved aside), pytest track1, UI types and tests |
| `oracle.sh` | clears `build/cache`, builds, runs the golden cases on a real Oracle (docker) |
| `fmt.sh` | `ruff format` + `ruff check` on the changed Python files only |
| `e2e.sh [name…]` | the headless-browser UI checks (`shots/*-check.mjs`), all or by name (`wizard`, `golden-run`…) |
| `rebuild.sh` | clears `build/cache`, `mapper build`, `mapper check`, shows what changed in `build/` |
| `shots.sh [name…]` | regenerates the guide's screenshots |
| `start_dev.sh [args…]` | the desktop app in dev mode (`cargo tauri dev`: Vite hot reload for the UI, Rust rebuild), with the settings Wayland needs |

Not scripts, on purpose: file edits go through the editor tools, not `python - <<EOF` rewrites.
