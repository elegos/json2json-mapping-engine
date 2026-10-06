# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The text of a release is the section of its version below; if there is none, the `Unreleased`
section (see `packaging/release.py`).

## [0.1.0] - 2026-10-06

First release. Work in progress: the engine and the desktop tool are usable, but not complete.

### Features

- The mapping engine and the desktop tool, with packages for Linux (AppImage), Windows (installer
  and portable zip) and macOS (dmg).
- Version control in the tool, with merging by rule.
- A portable `mapper` CLI for CI jobs.
