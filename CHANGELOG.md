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
