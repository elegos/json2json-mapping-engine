# Desktop tool (M6)

Tauri shell (`src-tauri/`, Rust) + React / AG Grid UI (`ui/`, TypeScript). It edits
`.fn.yaml` files as a rule grid and runs the `mapper` CLI; it contains no build logic
(docs/ARCHITECTURE.md, §Desktop tool).

Needs: Rust, Node, `cargo install tauri-cli --version '^2'`, the WebKitGTK 4.1 dev
packages (Fedora: `webkit2gtk4.1-devel`), and a Python >= 3.12 with the engine's
dependencies (`uv sync` at the repository root).

```sh
cd desktop/ui && npm install
cd .. && cargo tauri dev              # from desktop/ or desktop/src-tauri; runs the UI dev server and the app
(cd src-tauri && cargo test)                           # drives the real `mapper` on fixtures/orders-project
cd ../ui && npm test                   # grid model tests
```

Open `desktop/fixtures/orders-project` to try it. The engine is found through
`J2JME_ENGINE` (a directory holding `cli/`), else `<app-dir>/engine`, else this
checkout; Python is resolved as in §Python runtime, the engine's `.venv` first.

Running on Wayland: WebKitGTK may abort with `Error 71 (Protocol error) dispatching to
Wayland display`. Start with `GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1 cargo tauri dev`.
The app opens a project passed as its first argument or in `J2JME_PROJECT`.
