# dev_scripts

Scripts the development reuses; add one here when a command sequence is run more than once.

| Script | What it does |
|---|---|
| `check.sh` | what CI runs offline: ruff, basedpyright (local config moved aside), pytest track1, UI types and tests |
| `oracle.sh` | clears `build/cache`, builds, runs the golden cases on a real Oracle (docker) |
| `gix.sh [--rust]` | the git fallback (gitoxide, `desktop/gitfallback`): builds the helper and runs the git-side tests on both backends, the `git` binary and the helper |
| `fmt.sh` | `ruff format` + `ruff check` on the changed Python files only |
| `e2e.sh [name…]` | the headless-browser UI checks (`shots/*-check.mjs`), all or by name (`wizard`, `golden-run`…) |
| `rebuild.sh` | clears `build/cache`, `mapper build`, `mapper check`, shows what changed in `build/` |
| `python_floor.sh [version…]` | the golden cases run by the generated Python modules on other Pythons (default 3.10, 3.11, 3.14t): the floor the backend supports |
| `shots.sh [name…]` | regenerates the guide's screenshots |
| `package.sh linux|windows|macos…` | the desktop packages, built in the packaging image (`packaging/`): AppImage, Windows installer and portable zip, macOS dmg; output in `dist/packages/` |
| `ci_watch.sh <run> [job] [secs]` | follows a Forgejo Actions job (status, steps, log lines) until it ends; token from `.env` |
| `start_dev.sh [args…]` | the desktop app in dev mode (`cargo tauri dev`: Vite hot reload for the UI, Rust rebuild), restarting it when the Python engine changes, with the settings Wayland needs |

Not scripts, on purpose: file edits go through the editor tools, not `python - <<EOF` rewrites.
