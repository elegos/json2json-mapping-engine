# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The text of a release is the section of its version below; if there is none, the `Unreleased`
section (see `packaging/release.py`).

## [Unreleased]

### Added

- Version control in the tool (git mode): the **Version control…** panel with the changes, version
  notes, *Commit* (check, then build, then one commit of the sources and the generated files; *Commit
  as WIP* when the check fails), *Pull* (rebase) and *Push*.
- Merging by rule: a 3-way merge of `.fn.yaml` (rule by rule) and of `fn/*.fn` (function by
  function), as a git merge driver (`mapper merge-driver`, `mapper merge-driver-install`) that the
  tool installs by itself when a project is opened and before every pull. What both sides changed
  is settled in the tool, one choice per item.
- `build/compiled/manifest.json`: the hashes of the sources and of the outputs; `mapper check`
  compares the committed artifacts against it, and both pipelines run it.
- `mapper publish [--to DIR]` (also a button) and `mapper verify`: the generated files and the
  manifest written to a publish folder (`[publish] dir`, or a per-user folder), the manifest last, so
  a reader never sees half a set.
- `mapper artifacts status | ignore | track` and *Generated files…* in the tool: commit
  `build/compiled`, or leave generation to CI. New projects get a `.gitignore`.
- Engine version of a project (`[project] engine` in `mapper.toml`) and `mapper upgrade`: a newer
  tool updates the project after a warning, an older tool refuses unless the risk is accepted
  (`--allow-older-engine`); the version is never moved back.
- Git without git: when the `git` program is missing, the desktop tool uses a built-in gitoxide
  (gix 0.88) for status, commit, pull with rebase and push over https, with a login prompt.
- Every release also carries `j2jme-cli-linux-x86_64.tar.gz` (a portable `mapper`, no desktop) and
  `install-mapper.sh`, which installs the version a project's `mapper.toml` names (for CI jobs);
  `docs/CI.md` describes it.

### Not verified

- The panel and its dialogs in the running tool; the gitoxide fallback over SSH remotes, on
  Windows, with LFS and with submodules; the packaged builds with the new dependency.

## [0.1.0] - 2026-10-05

First release. Work in progress: the engine and the desktop tool are usable, but not complete.
Still missing:

- version control in the tool (save as a commit, pull and merge by rule);
- LLM assistance (validation suggestions, expression builder);
- an input and an output schema owned by each mapping;
- managing the golden cases from the tool, and running them there;
- the desktop preview;
- the `process` strategy for `@parallel` rules;
- a macOS package that is signed by Apple and notarised (the dmg is only ad-hoc or self-signed).

### Added

- The mapping engine and the desktop tool, with their first packages: an AppImage for Linux, an
  installer (for the user or for every user) and a portable zip for Windows, and a dmg for macOS.
