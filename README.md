# 🔀 json2json-mapping-engine

[![Latest release](https://git.giacomofurlan.name/elegos/json2json-mapping-engine/badges/release.svg)](https://git.giacomofurlan.name/elegos/json2json-mapping-engine/releases)
[![CI (latest commit)](https://git.giacomofurlan.name/elegos/json2json-mapping-engine/actions/workflows/ci.yml/badge.svg?branch=main)](https://git.giacomofurlan.name/elegos/json2json-mapping-engine/actions?workflow=ci.yml)
![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-3776AB?logo=python&logoColor=white)
![Status: work in progress](https://img.shields.io/badge/status-work%20in%20progress-orange)

![Target: PL/SQL](https://img.shields.io/badge/target-PL%2FSQL-008800?logo=oracle&logoColor=white) <!-- Done -->
![Target: Python](https://img.shields.io/badge/target-Python-008800?logo=oracle&logoColor=white) <!-- Done -->

A **compiled** mapping engine for JSON-to-JSON transformations. Write mapping rules in a
restricted, hard-typed subset of Python; the compiler turns them into native code for the target
runtime. No DSL interpreted at runtime, just ordinary compiled code.

## 📑 Contents

- [🔀 json2json-mapping-engine](#-json2json-mapping-engine)
  - [📑 Contents](#-contents)
  - [✨ Why](#-why)
  - [🧩 How it works](#-how-it-works)
  - [🎯 Targets](#-targets)
  - [🖥️ Desktop tool](#️-desktop-tool)
  - [📦 Install](#-install)
  - [🚀 Quick start](#-quick-start)
  - [🤖 CI](#-ci)
  - [🛠️ Development](#️-development)
  - [📚 Documentation](#-documentation)
  - [📜 License](#-license)

## ✨ Why

- 🧠 **Typed rules**: input and output are described by JSON Schemas; rules are type-checked
  before anything is generated.
- ⚡ **Native speed**: the output runs inside the target runtime, with no engine to deploy.
- 🔍 **Reviewable**: generated code is deterministic and can be committed, so it shows in diffs.
- 🧑‍🤝‍🧑 **Two ways to work**: hand-written `.map.py` (bootstrap) or functional rules in
  `.fn.yaml` that generate it (driven).
- 🔀 **Merge by rule**: a git merge driver that merges `.fn.yaml` rule by rule.

## 🧩 How it works

```
.fn.yaml ──► transpiler ──► .map.py ──┐
                                      ├──► compiler ──► target artifact (e.g. PL/SQL package)
JSON Schemas ──► stubs ───────────────┘
```

Everything up to the type checker is target-agnostic; only the backend emits code.
Project settings live in `mapper.toml`.

## 🎯 Targets

| Target | State |
|---|---|
| PL/SQL (Oracle) | ✅ reference implementation, see [`docs/backends/plsql.md`](docs/backends/plsql.md) |
| Python | ✅ complete (generated modules need Python 3.10+) |

Writing another one: [`docs/backends/writing-a-backend.md`](docs/backends/writing-a-backend.md).

## 🖥️ Desktop tool

A Tauri app (Linux AppImage, Windows installer and portable zip, macOS dmg) to edit rules in a
grid, try a mapping, run the checks and use git (commit, pull, push) without leaving it.
See [`desktop/README.md`](desktop/README.md).

## 📦 Install

- 📥 **Desktop tool and CLI**: download from the project's releases page (see the release badge).
- 🐍 **From source**: Python >= 3.14 and [uv](https://docs.astral.sh/uv/) for the engine and the
  `mapper` CLI (headless use, CI).

```sh
uv sync --all-extras --dev
uv run mapper --help
```

- 🖥️ **Desktop tool from source**: it is the app, not `mapper`, that people work with. On top of
  the Python setup above it needs:
  - [Rust](https://rustup.rs) (stable) and a C compiler;
  - [Node.js](https://nodejs.org) and npm (the React UI);
  - `cargo install tauri-cli --version '^2'`;
  - on Linux, the WebKitGTK 4.1 dev packages (Fedora: `webkit2gtk4.1-devel`).

```sh
(cd desktop/ui && npm install)
dev_scripts/start_dev.sh      # the app in dev mode, with the settings Wayland needs
```

Details in [`desktop/README.md`](desktop/README.md).

## 🚀 Quick start

```sh
mapper build      # transpile (driven mode) + compile into build/compiled/
mapper check      # regenerate and fail if it differs from the committed files
mapper publish    # check, build, then publish the files and manifest.json
mapper verify     # check a published folder against its manifest.json
```

Try it on the sample project in `desktop/fixtures/orders-project`.

## 🤖 CI

`mapper check` and `mapper build` need no Python on the runner:
`packaging/install-mapper.sh` installs the engine version pinned in `mapper.toml`.
Works on Forgejo Actions and GitHub Actions: [`docs/CI.md`](docs/CI.md).

## 🛠️ Development

```sh
uv run ruff check .
uv run basedpyright
uv run mapper test --integration   # needs an Oracle database
```

Both pipelines (`.forgejo/workflows` and `.github/workflows`) are kept in sync.

## 📚 Documentation

- 🏛️ [Architecture](docs/ARCHITECTURE.md)
- 🗺️ [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- 🤖 [Running `mapper` in CI](docs/CI.md)
- 🔌 [PL/SQL backend](docs/backends/plsql.md) · [Writing a backend](docs/backends/writing-a-backend.md)
- 🧪 [Oracle runtime spike notes](docs/spike-notes.md)
- 📝 [Changelog](CHANGELOG.md)

## 📜 License

Copyright (C) 2026 Giacomo Furlan.

Licensed under the **GNU General Public License v3.0** (GPLv3) — see
[`LICENSE`](LICENSE) for the full text.

**Generated output exception**: code that the engine generates from your mapping rules (PL/SQL
packages, Python modules, dataclasses, or any other backend target) is **not** covered by the
GPL and may be used, distributed, and relicensed under terms of your choosing. Only the engine
itself (compiler, transpiler, CLI, desktop tool) is GPLv3; see the exception's exact terms at
the end of [`LICENSE`](LICENSE).
