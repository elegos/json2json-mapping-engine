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

## The guide's screenshots

The figures of the in-app guide (`ui/src/guide/`) use screenshots taken by a script, with the
numbered boxes found in the page itself, so they follow the UI:

```sh
cd desktop/ui
npx playwright-core install chromium   # once, or any Chromium Playwright can find
npm run shots                          # all of them; or: node shots/run.mjs grid lookups
node shots/preview.mjs "The grid" out.png    # a guide page as the tool draws it
```

`shots/spec.mjs` lists what to photograph and what to number (CSS selectors). The script runs the
real UI in a headless browser on a copy of the tutorial project; `shots/bridge.mjs` stands in for
the Tauri shell and answers with the real `mapper`. A shot that does not come out well can be
taken by hand: put the PNG in `src/guide/img/` and give the figure its own `callouts` in the page.
