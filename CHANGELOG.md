# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The text of a release is the section of its version below; if there is none, the `Unreleased`
section (see `packaging/release.py`).

## [Unreleased]

### Features

- The check suggests the closest name ("did you mean 'x'?") for a field, reference, alias or
  function that does not exist.
- Expression syntax errors say what to write instead (`&&` → `and`, `cond ? a : b` → `a if cond
  else b`, …) and where the expression stopped.
- The check reports an unknown function in an expression (it was found only by the build) and
  a bare `return` on a required field.

## [0.2.0] - 2026-10-07

### Features

- Desktop tool: adding a field, object or loop opens a dialog asking its name and, for a field,
  its type and whether it is required; the grid scrolls to the new rule.
- Desktop tool: rules can be reordered by dragging, among the rules of their own level (the root, an
  object or a loop). A gap opens where the rule will land and the rule lights up once dropped.
- Desktop tool: Description and Notes open in a text area (Shift+Enter breaks a line) and are read in
  full, line breaks included, in a scrollable bubble over the cell.
- `mapper serve` `add_rule` accepts an optional name, type and required.
- The software is licensed under the GPLv3, with an exception for generated output; the licence is
  shown in the README, the CLI and the desktop tool's help.

### Changed

- Desktop tool: Transpile, Build and Check are one **Check…** button; in Developer mode its caret
  lists Transpile, Build, Check… and Publish.
- Desktop tool: *Publish folder*, *Build folder* and *Generated files* moved from the toolbar to
  Project properties, under *This machine and repository*, with their current values.

### Fixed

- Desktop tool: the last rows of the grid were covered by the horizontal scrollbar on systems with
  overlay scrollbars.

### Documentation

- The README explains how to get past the Windows SmartScreen warning.
- The in-app guide, the tour and the docs follow the new toolbar.

## [0.1.0] - 2026-10-06

First release. Work in progress: the engine and the desktop tool are usable, but not complete.

### Features

- The mapping engine and the desktop tool, with packages for Linux (AppImage), Windows (installer
  and portable zip) and macOS (dmg).
- Version control in the tool, with merging by rule.
- A portable `mapper` CLI for CI jobs.
