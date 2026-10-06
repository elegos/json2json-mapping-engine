# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The text of a release is the section of its version below; if there is none, the `Unreleased`
section (see `packaging/release.py`).

## [Unreleased]

## [0.1.0] - 2026-10-05

First release. Work in progress: the engine and the desktop tool are usable, but not complete.
Still missing:

- LLM assistance (validation suggestions, expression builder);
- the rest of the schemas owned by each mapping (a picker among the project's own, a confirmation
  before replacing one);
- running the golden cases from the tool (they can be listed, imported, renamed and deleted there);
- the desktop preview;
- the `process` strategy for `@parallel` rules;
- a macOS package that is signed by Apple and notarised (the dmg is only ad-hoc or self-signed).

### Features

- The mapping engine and the desktop tool, with their first packages: an AppImage for Linux, an
  installer (for the user or for every user) and a portable zip for Windows, and a dmg for macOS.
- Version control in the tool (git mode): the **Version control…** panel with the changes, version
  notes, *Commit* (check, then build, then one commit of the sources and the generated files; *Commit
  as WIP* when the check fails), *Pull* (rebase) and *Push*.
- Merging by rule: a 3-way merge of `.fn.yaml` (rule by rule) and of `fn/*.fn` (function by
  function), as a git merge driver (`mapper merge-driver`, `mapper merge-driver-install`) that the
  tool installs by itself when a project is opened and before every pull. What both sides changed
  is settled in the tool, one choice per item.
- Git without git: when the `git` program is missing, the desktop tool uses a built-in gitoxide
  (gix 0.88) for init, status, commit, pull with rebase and push over https, with a login prompt.
  Git never opens the desktop's password window (`ksshaskpass`, ...) behind the tool's back.
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
- Every release also carries `j2jme-cli-linux-x86_64.tar.gz` (a portable `mapper`, no desktop) and
  `install-mapper.sh`, which installs the version a project's `mapper.toml` names (for CI jobs);
  `docs/CI.md` describes it.
- Projects in a synced folder (OneDrive, SharePoint, Dropbox, ...): the tool recognises them by
  their path and asks for a folder on the machine to build in (per user and project, *Build folder…*
  to change it); nothing generated is written in the synced folder. `mapper` stops there unless
  `J2JME_BUILD_DIR` points elsewhere (or `J2JME_ALLOW_SYNCED=1` for a folder that only looks synced).
- Teamwork through a synced folder: when the file in the folder changed since you saw it, a save
  merges your edit with it rule by rule (function by function in `fn/*.fn`) and asks only about what
  both changed; the window reads the open mapping again when it comes back to the front, and the
  conflict copies the sync makes (`name-PC.fn.yaml`) are offered for merge. Files are saved whole
  (temporary file and rename).
- Presence in a synced folder: the footer says who else has a mapping open ("bob is editing
  orders"), advisory, nothing is locked.
- Loading an input or an output schema sends back to review the validated rules it no longer fits
  (a Source or a Target that is gone or has another type), with a note saying why.
- A git repository inside a synced folder is refused: the tool explains why (the sync corrupts
  `.git`) and offers to delete `.git` (the files stay, the history goes); if you decline, the project
  is not opened. A project outside any repository is offered `git init` (optional).

### Not verified

- The panel and its dialogs in the running tool (also the synced-folder dialog); the gitoxide
  fallback over SSH remotes, on a real Windows machine, with LFS and with submodules; the macOS
  package, which builds with the new dependency but has not been run on a Mac; real OneDrive and
  SharePoint folders.
