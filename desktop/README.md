# Desktop tool (M6)

Tauri shell (`src-tauri/`, Rust) + React / AG Grid UI (`ui/`, TypeScript). It edits
`.fn.yaml` files as a rule grid and runs the `mapper` CLI; it contains no build logic
(docs/ARCHITECTURE.md, §Desktop tool).

Needs: Rust, Node, `cargo install tauri-cli --version '^2'`, the WebKitGTK 4.1 dev
packages (Fedora: `webkit2gtk4.1-devel`), and a Python >= 3.12 with the engine's
dependencies (`uv sync` at the repository root).

```sh
cd desktop/ui && npm install
cd ../src-tauri && cargo tauri dev     # runs the UI dev server and the app
cargo test                             # drives the real `mapper` on fixtures/orders-project
cd ../ui && npm test                   # grid model tests
```

Open `desktop/fixtures/orders-project` to try it. The engine is found through
`J2JME_ENGINE` (a directory holding `cli/`), else `<app-dir>/engine`, else this
checkout; Python is resolved as in §Python runtime, the engine's `.venv` first.
