# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The text of a release is the section of its version below; if there is none, the `Unreleased`
section (see `packaging/release.py`).

## [Unreleased]

### Features

- Loops: `order_by: "<expression> [asc|desc] [nulls first|last], ..."` (SQL's `order by`) replaces
  `sort`: keys are expressions of the element, several keys, a direction and where the elements with no
  key go (last by default). The earlier `sort: {key, reverse}` still loads and is written back as
  `order_by`. The Python backend now runs a sorted loop at all (it passed the key as text to Python's
  `sorted`, which raised on every run), and PL/SQL orders by the computed keys with a stable sort that
  copies into a new array. Desktop: an *Order the list by* editor in the loop options.
- Aggregates inside aggregates, to any depth (`count(l for l in $.lines if not any(any(i.ref == l.ref for
  i in p.items) for p in $.packages))`), and two new ones, `any(cond for x in list)` and `all(...)`
  (Python's truthiness; the loop stops at the first element that decides). On PL/SQL an aggregate in the
  condition of an `if` of a rule function is now computed first too.
- A selection's condition can hold an aggregate over a list of the candidate:
  `$.packages[any(i.ref == @2.ref for i in items)].vol`: the first package that holds this line.
- Selections: `$.list[condition order by <keys>]` (or `$.list[order by <keys>]`) takes the first element
  in that order: the event with the highest rank, the earliest date. The same clause as a loop's
  `order_by`; it works in a path of a field, in an expression and in the Source of a selecting object.
- Loops: `when_empty: omit | list` says whether a list with no element is left out or written as `[]`.
  **Behaviour change** (alpha): unset, an optional list (one the output schema does not require) is now
  left out when empty; before, every list was written empty. A required list is still written empty,
  and `omit` on one is refused by the check.
- A loop's `source` can start from an outer loop (`@2.refs[*]`, `@line.refs[*]`), as a `filter` could;
  the check rejected it.
- Desktop: an icon beside each loop opens *Loop options*: label, order (`sort`), first `@index` number,
  *when there is nothing to list*, parallel degree. `sort`, `index_start` and `parallel` had no editor
  before, only the YAML.
- `x in ("A", "B")` and `x not in (...)` with a literal list now build on PL/SQL too (`IN (...)`; a
  missing value is in nothing, as in Python).
- `mapper import assemble` builds the working copy for the project's target (`mapper.toml`, no
  database), as `mapper build` does, and reports what the target cannot build on the rule that
  causes it. The check is the same for every backend; the backends are not (a function one has no
  implementation of): a rule that passed the check but would not build for Oracle is now an error of
  the plan, not a surprise of the build.

### Fixed

- An optional object (a property the output schema does not require) that is left out by a guard or a
  selection is no longer an error. The check asked the schema to allow `null` for it, and the compiler
  refused it at the top of a mapping, though omitting a non-required property is exactly what the
  language means. Only a **required** property is still refused.

## [0.4.0] - 2026-10-15

### Features

- Import of a long document (above about 80 units) in batches: a *survey* run classifies every unit
  (`units.json`), the code writes the plain ones itself (constants, copies, implied objects) and cuts
  the rest into batches, and several assistant runs translate them at once, handing their rules to
  `mapper import add` (checked and merged, with the evidence text and hashes filled from the document)
  instead of rewriting the plan. New: `mapper import queue | add | ask | answers | batch | gaps`,
  `mapper import run --concurrency --batch-size`, the plan lock (`ir.json.lock`). Docs:
  `docs/import/BATCHES.md`.
- Questions are asked while the run goes on (`mapper import ask`, deduplicated) and shown on the run
  screen next to the progress; the run does not wait, the rules that depended on an answer are read
  again at the end. The survey lists what the engine is expected to lack before anything is translated.
- An import begun in one run goes on in batches (*Translate the rest* on the main import page): the
  survey classifies only the units the plan has no rule for.
- Import: a worker that tries to write the plan is refused on purpose (`ir.json` is changed only by
  `mapper import add`); the refusal is not offered to the user as a permission.
- Import: *Delete…* on each import of the main import page (also one whose run left no plan) drops its
  plan, answers and working copy; documents, profiles and rules already applied stay.

## [0.3.1] - 2026-10-14

### Changed

- Windows installer (NSIS): the application's icon instead of the generic one, and the version and
  the commit in its title and welcome page (`J2JME Desktop 0.3.1 (abc1234)`).
- Desktop: the import view fills the window in width and height (no fixed sizes), with minimum sizes
  instead.

### Features

- `mapper import outline | rows | blocks | find`: compact, sliceable text views of an extracted
  document (one line per row or block), so that the assistant reads a spreadsheet of hundreds of rows
  in slices with no permission beyond `mapper`; the skill uses them.
- Import: the input and output JSON Schemas can be named up front (*Input / Output JSON Schema* in the
  wizard, `mapper import run --input-schema / --output-schema`). They are copied into the project
  (`schemas/<mapping>_input.schema.json`, else `import/schemas/`) so the assistant reads them like any
  project file, and the skill takes them as provided.
- Import: when the assistant is refused a call (a permission), the failed run lists the calls and
  *Allow and run again* (`--allow <rule>`) repeats the run with them allowed.

### Fixed

- Import on Windows: the assistant could not run `mapper` ("mapper isn't found in bash"), because the
  shim in its PATH was only `mapper.cmd`, which the Bash of Git for Windows does not run. It now
  also gets an extension-less `mapper`.
- Import from the installed application: the readers for xlsx, docx and pdf (`openpyxl`,
  `python-docx`, `pdfminer-six`, the `import` extra) were not in the bundled engine, so
  `mapper import extract` failed there. They are now staged with it.

## [0.3.0] - 2026-10-14

### Features

- Validation of the input and the output: a `validations:` section in the functional file with the
  JSON Schema check of each side (off by default; Oracle 23ai `DBMS_JSON_SCHEMA`, Python
  `jsonschema`; best effort: `format` is not checked) and extra checks (`expect` on `$`, `code`,
  `message`, `reject` or `warn`). A `reject` runs no rule and gives no output; every failed check is
  reported (`p_report` of `map_<id>_safe` / a third result, `MappingRejected` / the reserved error
  with `rejected`). Golden cases: `<case>.expected_rejected.json`, `.expected_warnings.json`. New
  built-in `is_digits`. The import turns "reject if..." statements into validations. Desktop: the
  *Validations (I: n, O: m)* tab, and the golden cases' expected rejected / warnings files.
- `mapper import extract | assemble | test | apply`: read a functional document (xlsx, docx, pdf,
  txt, md) into a normalized form, build and check a `.fn.yaml` from an import plan, run the plan's
  cases against it, and write it to the project (`pip install` extra `import` for the readers).
- Desktop: *Import a document…* in the start wizard, full screen: pick a functional document and an
  installed assistant (Claude Code or Codex), follow and cancel the run, answer its questions, review
  the plan (rules with their evidence, confidence and check; validations; lookups; cases;
  discrepancies; coverage) and apply it. `mapper import providers | run` and the `import_*` ops of
  the worker are the same thing from the command line.
- More built-ins, so that patterns are the last resort and not the first: `upper`, `lower`, `trim`,
  `length`, `substring`, `left`, `right`, `pad_left`, `pad_right`, `contains`, `starts_with`,
  `ends_with`, `abs`, `floor`, `ceil` and `format_date` (a date written in a format). Python and
  PL/SQL backends, golden mapping `builtins_more`. Library 1.1.0.
- A lookup table can be empty (`entries` may be left out): the import writes a table the document does
  not give, named and empty, so the rules that read it already run. It finds nothing until filled in.
- Groups: an `object` with `output: $` and a `guard` writes its rules into the output root when
  the guard holds. It is how a mapping produces one of several shapes (`oneOf`): a group per shape,
  guards written by the author; the check asks of the root only what every shape requires. The
  import asks which shape each part of the document is and in which order the guards apply.
- Loops: `source: $` runs over the document itself (one element: a list with a single element
  built from the message, or, with a `filter`, a block written only when a condition holds), and
  several loops can add to one output list in order. A list missing from the document has no
  elements on PL/SQL too (the loop raised ORA-30625). Golden mapping `document_loop`.
- More built-ins: `parse_timestamp` (a date and time with a month name or AM/PM), `days_between`,
  `add_days`, `split_last` and `join` (a list, or a comprehension, in one text); `to_utc` and
  `rfc3339_normalize` take the number of fraction digits (milliseconds). Python and PL/SQL,
  golden mapping `builtins_dates`.
- Aggregates over some elements or a computed value: `count(i for i in $.items if i.ok)`,
  `sum(abs(i.qty) for i in $.items)`, likewise `max`, `min`, `avg`. One loop on both backends,
  the element's fields are checked against the schema. An aggregate may now be part of a larger
  expression on PL/SQL too (`round(sum(...), 2)`). Golden mapping `aggregate_by`.
- The check suggests the closest name ("did you mean 'x'?") for a field, reference, alias or
  function that does not exist.
- Expression syntax errors say what to write instead (`&&` → `and`, `cond ? a : b` → `a if cond
  else b`, …) and where the expression stopped.
- The check reports an unknown function in an expression (it was found only by the build) and
  a bare `return` on a required field.

### Changed

- A value that is `None` (a missing source, a lookup that finds nothing, `max` of an empty set) is
  no longer written as `null`: the field is left out, as a bare `return` does. `Null`, the explicit
  null, still writes `null`. Both backends, in a rule, a direct assignment, a field of an object and
  an element of a list. Golden cases that expected `null` for a missing value now expect no field.

### Fixes

- Groups (`object` with `output: $` and a `guard`): a list written inside a group exists only when
  the group's guard holds (a DELETE message no longer gets the POST group's empty `rows: []`), on
  both backends; loops with a `filter`, `sort` or `enumerate` inside a group are lowered like the
  ones at the top (the PL/SQL build stopped on `continue`); an output schema that is a `oneOf` at
  the root now builds (the mapping writes the union of the shapes' fields).
- `mapper import assemble` reports a rule that is its own parent (or part of a ring of parents) in
  `skipped`, instead of writing a file without it; the import plan accepts the lookup status
  `partial`, and the skill says how to number rules, write a target that is a path, get a whole
  number from a rounded one, and leave out an empty list.
- A mapping whose output schema is one of several shapes (`oneOf`) was refused by the compiler
  (`KeyError`): the root is now the union of the shapes (a field only some have is optional).
- Several loops inside an `object` can add to one list (the transpiler refused it: "duplicate
  output field"). `count` of a missing list is 0, and `sum`, `max`, `min`, `avg` over `(list,
  "field")` follow the rules of the comprehension form on Oracle too (a missing value is skipped, a
  missing list is empty).
- The compiler's type check: a property the schema does not require may be left out (a rule that
  can omit it was refused); a `const` or `enum` without a `type` is typed by its values (it was an
  opaque object); `abs` of a whole number is a whole number and `floor`/`ceil` give whole numbers
  (an integer field refused them); a field named like a keyword is typed through the schema.
- Sums and products of decimal numbers on the Python backend are the database's
  (`0.1 + 0.2` is `0.3`, `130.83` not `130.82999999999998`).
- `mapper import assemble` treats a required output field that no rule writes yet (a function gap,
  a missing lookup) as a gap, not a failure: the cases still run; `apply` asks for `--force`.
  The Word reader no longer marks the cells of a table without merged cells as continuations.
- A field named like a Python keyword (`$.return.number`, `i.from`) can be read, in a path, an
  expression and a loop source, on both backends (it was a syntax error in the generated code).
- `parse_date` of a missing text gives nothing on the Python backend (it failed; Oracle gave null).
- `mapper import test` no longer ends in a traceback when the working copy checks but does not
  compile: the cases are reported as not run, with the cause.
- `max`, `min`, `sum`, `avg` skip a missing value (as SQL does) instead of failing on the Python
  backend, and `max`, `min`, `avg` of nothing are null on both; `round`, `trunc`, `abs`, `floor`,
  `ceil` of a missing value are null on the Python backend too (they were an error there).
- The check no longer rejects `@index` as a source or in an expression, and a loop that numbers
  its elements (`index_start`) now runs on the Python backend.

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
