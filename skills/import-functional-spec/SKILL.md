---
name: import-functional-spec
description: Import a functional specification (spreadsheet, Word, PDF, plain text; table, prose or pseudo-code) into a json2json mapping project. Reads the document, discovers its conventions, asks the user about what is unclear, and produces a reviewable import plan (IR) with a best-guess `.fn.yaml` rule for each requirement. Use it when the wizard of the desktop tool, or the user, asks to import a mapping from a document.
---

# Import a functional specification

You turn a functional document into an **import plan** (`references/ir.schema.json`) for a
json2json mapping project. You do **not** write rules into the project: the wizard shows the plan,
the user corrects it, and the rules are generated from it. Everything below is about being right
where the document is clear and honest where it is not.

Documents differ wildly (a table per message, requirement sentences, pseudo-code, one prose
paragraph per field; with or without JSON Schemas; any language). **No style is known in advance.**
What varies is a *convention* (index base, array notation, null rule, date dialect, scope of a
condition, meaning of a colour...), recorded in a **profile** and asked about when the evidence is thin.

## Inputs and outputs

Given: the document path; the project directory; optionally the mapping id, a profile name, an
existing plan (re-run), and the answers already given. Read these files if they exist:

| File | What |
|---|---|
| `import/<mapping>/ir.json` | the plan so far (resume from it) |
| `import/profiles/<name>.profile.yaml` | conventions (`references/profile.schema.json`) |
| `schemas/<mapping>_input|output.schema.json` | the mapping's JSON Schemas, if any |
| `mappings/functional/<mapping>.fn.yaml` | existing rules (never overwritten without asking) |

Produce: `import/<mapping>/ir.json` (validates against the schema), an updated profile, and one
final line on stdout (see `references/protocol.md`). Do not modify anything else.

## The run is resumable and stateless

Each run reads the files, does all the work it can, writes the files, and stops either **needing
answers** (open `questions`) or **ready for review**. The wizard writes the user's answers into the
plan (`questions[].answer`, `status: answered`) and starts a new run, which continues from there.
Never wait for an answer inside a run and never assume one that matters (see *Asking*).

## Procedure

### 0. Environment
- The functions you may call are **only** those printed by `mapper functions --json`. Run it at the
  start of every run; do not rely on memory or on this file. Parameters, `doc` and `origin` tell
  what each one does. Project functions (`fn/*.fn`) may replace built-ins.
- You never write a `.fn.yaml`. Each rule's `proposal.fn_rule` is a fragment with an `id`, and
  `proposal.parent_rule` names the `object`/`loop` fn rule it sits in (absent at the top). Run
  `mapper import assemble <mapping>` from the project directory: it builds the working copy
  `import/<mapping>/work/<mapping>.fn.yaml` (lookups first, then the rules nested by `parent_rule`),
  checks it, and writes each rule's `proposal.check`. A rule that does not pass is retried at most
  twice with the error as input, then left as a flagged guess. The check is only as good as the
  schemas it found: `schemas_found` false means it could not vouch for any path, so say so in the
  rule's reasons. A pass is necessary, not sufficient (`references/expression-language.md`).

### 1. Read the document
- Never read a binary format as bytes. Run `mapper import extract <file> --out import/<mapping>/document.json` (xlsx, docx, pdf, txt, md), which gives the **normalized document**
  (`references/normalized-document.schema.json`): blocks in reading order with their location,
  tables with merged cells already resolved, formatting that may carry meaning (fill, strike-through,
  font colour), and running headers/footers marked as noise. Read `warnings` in the
  result (formulas shown as text, hidden sheets or columns, tracked changes, PDF tables not
  reconstructed) and carry them into the plan's flags. If the command fails because a library is
  missing, tell the wizard (`failed`, reason `extractor_unavailable`); do not read the file by other means.
- If the document has **no extractable text** (scan, image), stop there: write a minimal plan with
  `mapping` unknown (the mapping id given, or `unknown`), no rules, `coverage.units_total: 0`, one
  `coverage.not_imported` entry for the whole document (reason `unreadable`), an empty profile
  (no conventions) and a single question with scope `mapping` asking for a text version or an
  OCR (options: "a text version", "run an OCR", "give up"). Status `needs_answers`. Never produce
  rules from nothing. If an OCR is available, mark every rule `low` at best and ask the user to
  confirm the transcription.
- Record the **version**: file name, version sheet/section, column, header, document properties. Values that name the
  same version (`v3`, `3.0`, `rev 3`) are one value, written as the document writes it most fully;
  several different values: ask which prevails. None: `1.0`, `origin: assumed_default`.

### 2. Choose the mapping
- One document may hold several mappings (sheets, chapters, one per verb or direction). List them
  (name, rule count, probable input/output) and **ask which to import**. Never import all silently.
- Record all of them in `document.mappings_found` (id, location, rule count, `imported`).
- Rules that apply to every mapping (a general-rules sheet, a header note, a conventions section)
  are collected once and attached to each rule as `inherited_context`.

### 3. Profile
- A profile is a file `import/profiles/<name>.profile.yaml`; `<name>` is lowercase letters, digits,
  `-` and `_`. Use the name the wizard gave. If none, name it after the document's style when
  other mappings are likely to share it (`requirements-table`, `pseudo-code`), else after the
  mapping id.
- If the user did not pick one, propose the project's profiles (`description`, mappings served) or a
  new one. A reused profile is **checked against this document**: every convention the evidence
  contradicts, and every feature of the document the profile does not cover, becomes a question
  with scope `profile`.
- Discover conventions with `references/conventions.md` (the topics to look for, where to look, what
  to ask). Look first where documents state conventions (read-me, general rules, intro, legend,
  footnotes), then at the evidence in the rules. A convention seen only once is `inferred` and
  `confirmed: false`; one the document states itself is `document_evidence` and counts as confirmed
  (its source is in the plan). A rule that relies on an unconfirmed convention gets the flag
  `unconfirmed_convention` (in `confidence.flags`) and the convention's topic in its reasons.
- Formatting is meaningful only when a legend or the user says so; otherwise record the marker with
  `meaning_origin: guess|unknown` and ask when it changes the reading (e.g. strike-through).

### 4. Schemas
- Provided in the project, or found in the document (appendix, attached file, pasted payload), or
  inferred from the paths and sample values, or none. `inferred` is a **proposal** the user must
  confirm; record `origin` honestly. With no schema, paths are unverified and every rule is at most
  `guess` (`no_schema` flag). Do not invent field names that are not in the text: when the
  document only gives a label, propose a name and say it is proposed.
- Names in the document's own text (a schema file it mentions) that differ from the files
  provided are an info `discrepancy`; the provided files win.
- A schema that is **one of several shapes** (`oneOf` / `anyOf`, e.g. a body for POST and another
  for DELETE): the mapping has no such notion. Each shape is a **group** you write, an `object`
  rule with `output: $` and a `guard` (`references/expression-language.md`), holding the rules of
  that shape; the guards are yours to write and must exclude one another. **Ask** (scope
  `mapping`): which shape each part of the document is (a sheet, a section), the condition that
  selects it, and **the order in which the guards apply**: it is not necessarily the order of the
  schema (A, B, C) and the first that holds should be the right one. Propose the document's order
  and a condition read from the document (a column, an operation name); say what a message that
  matches none gets (nothing is written). A rule that writes in several shapes is repeated in
  each group.
- Compare the document with the schemas: field in the document and not in the schema (with the
  closest name), mandatory schema field never mapped, type, cardinality or enum mismatches,
  mandatory/optional conflicts. Each is a `discrepancy`.

### 5. Rules
For each unit of the document that holds a rule (or the whole document, when it is prose):
1. Keep the **evidence** verbatim: text, every cell/paragraph it spans, the inherited context (band
   title, loop, root path, a condition stated for the section) and the review dialogue found beside it.
2. Write the **interpretation** in plain words: what the output is, from what, under which
   condition, what happens when a value is missing. List each **assumption** with its basis
   (`profile`, `document_evidence`, `user_answer`, `guess`). If a reading is a guess, do not hide it.
3. Decide `intent` and the **scope of conditions** (row / section / message) from the document, not
   from habit.
4. Anything you cannot decide and that changes the output becomes a **question** (see *Asking*);
   keep working with the most plausible reading marked as an assumption.
5. A row marked as removed or empty is a unit that is not imported (reason). A title is not a unit
   but is still listed in `coverage.not_imported`.
6. A statement that shapes the whole message (one notice per order, skip the ones without a weight,
   a root path, an ordering) is **its own rule** (`intent: loop` or `object`) carrying the filter;
   it is also attached as `inherited_context` to the field rules it affects. Context alone
   generates nothing in the project.

7. A statement that **refuses the message** (or flags it) when a condition fails ("reject the
   message if the VAT number is not 11 digits", "mandatory when X is present, else reject", "warn
   when the total is above...") is neither a field rule nor a function gap: it is a **validation**,
   an entry of the plan's `validations` array (`references/ir.schema.json`). Give it `side`
   (`input`: the message before any rule runs, the usual one; `output`: the result), `expect` (the
   condition that must **hold**, written on `$`), `code` (the document's requirement id, e.g.
   `REQ-16`, else `UPPER_SNAKE`), `message` and `action` (`reject`, unless the document only asks
   to report or warn). Evidence, interpretation, confidence and review are as for a rule. A condition
   that skips one element of a list is a loop `filter`, not a validation. The condition says what a
   missing value means: only a **true** condition passes, so an optional field is
   `not $.vatId or (...)` and a mandatory one is `$.vatId`. All the failed checks are reported
   together, so write each independently. Whether the mapping also validates against the JSON
   Schema (`schema_validation.input` / `.output`) is off unless the document or the user asks for
   it (the host may validate upstream or downstream): ask once (scope `mapping`) when the document
   says the message "must conform to" the schema.

### 6. Translate
- A plan rule's `id` is `<target>@<location>` (`references/ir.schema.json`); the `fn_rule.id` is an
  identifier of letters, digits and `_` (not starting with a digit), derived from the target path
  (`student_number`, `lines_sku`). It must be unique in the mapping.
- A target nested in an object (`student.id`, a dotted path) or a list needs the `object` / `loop`
  rule that holds it. When no row of the document defines that container, write it as its own plan
  rule (`intent: structure`, evidence = the first row that uses it, `proposal.parent_rule` for its
  children); it is generated, not invented, and is counted with its children, not as a unit.
- From the interpretation, write the `.fn.yaml` rule (`proposal.fn_rule`): `kind`, `field`,
  `source`, `transform.expression`, `description`. Use only catalogue functions and the syntax in
  `references/expression-language.md` (file skeleton, anchors, what is not a filter). Prefer a
  catalogue function to a pattern: `regexp_*` is the very last resort (slower, and the one place the
  backends differ).
- The rule's `description` gets the interpretation, the assumptions and, for a guess, the original
  wording: **"GUESS from: '<verbatim text>'. <what was assumed>"**. This is where the functional will
  read it.
- A validation's `expect` uses the same expression language (`references/expression-language.md`),
  with `$` the checked document; `mapper import assemble` checks it against the input schema (or the
  output schema for `side: output`) and records the result in the validation's `check`.
- Missing function: do **not** invent a name or fake it with something else. Leave out `fn_rule`,
  put `functions_missing` with what is needed (`proposal.check` is then absent or `ran: false`), flag
  `function_gap`. An operation that would only be possible as a pattern is still listed if a plain
  function would do the job (e.g. case change, a part of a text, a date in another format): say so
  in `suggestion`.
- Write `back_translation`: describe what the generated rule does using only the proposal; if it
  differs from the interpretation, fix one of the two.
- Set `validation.needs_review: true` on every **field** rule that is not `high`, inside its
  `proposal.fn_rule` (the plan rule itself has no `validation` key; its doubt is `confidence`) (an `object`, a
  `loop` and a `lookup` have no such key: their doubt lives in the plan's `confidence`; `assemble`
  drops the key if you write it).
- A rule needing a lookup table the document does not give: write the rule as usual, and the table
  in the plan's `lookups` with the name the rule reads (`@UOM`), the entries the document does
  give (partial ones too) and status `missing` or `partial`; with none, the table is empty. Flag
  `missing_lookup`, and ask for the entries in a question with scope `mapping`. `assemble` writes
  the (empty) table, so the rule runs and finds nothing until it is filled in: never invent an
  entry, and give the rule a default that says so. `assemble` reports a required output field with
  no rule as a `gap`, not as a failure of the plan: the cases still run, and the missing field is
  the only difference.
- A sentence that writes a null on purpose ("send null") is `Null`; "not sent" / "omitted" is
  `None` (`references/expression-language.md`).

### 7. Verify
- Cases found in the document (sample values, payload sheets, worked examples) go to `tests`:
  `input` is a **complete** source message and `expected` the output for it, complete or, with
  `partial: true`, only the part the document shows. Missing input fields are left out, not
  invented. `trust`: `paired_in_document` only when input and expected output are given together; samples from
  different places are `inferred_pairing`; a lone value is `single_value`. A message the document
  says is refused has no output: give `expected_rejected` (the codes of the checks that reject it,
  all of them) instead of `expected`, and `expected_warnings` for the codes that must be reported. Run them with
  `mapper import test <mapping>`, which records `result` and `detail` per case and adds a
  `sample_contradicts_rule` discrepancy for a failure; a failure lowers the rule's confidence. Never change a rule just
  to make a doubtful sample pass.
- Consistency checks for the report: removed in the document but a rule still present; mandatory
  `N` with "reject if empty" (a validation `$.x`, `reject`); a target mapped twice differently; a lookup referenced but absent; a
  reference to a rule or row that does not exist; a row's own rule that contradicts a general rule
  (`rule_conflicts_with_general_rule`: say which prevails and why).
- Fill `coverage`. A **unit** is a table row, a requirement sentence/paragraph, a pseudo-code
  statement or a definition that governs a rule. Titles, bands, version sheets, notation
  paragraphs, structural wrappers and attached footnotes are **not** units (`units_total` does not
  count them) but nothing disappears: each is listed in `not_imported` with its reason (`header_or_title`,
  `not_a_rule` for a version history or a notation paragraph, or
  `footnote_or_definition_used_by_a_rule` for one a rule relies on: it is used, not lost). Every unit is imported, imported with doubt, or not imported (reason);
  a unit that yields several rules counts once. A unit is `imported_with_doubt` when any of its
  rules is not `high` or carries a flag (`ambiguous`, `contradiction`, `unconfirmed_convention`,
  `missing_lookup`...), else `imported`. `document.mappings_found[].rules` counts units too.

### 8. Stop
Write the profile first, then the plan with the profile's hash (`profile.sha256`: SHA-256 of the
profile file's bytes), then end with the status line. If open questions remain, the status
is `needs_answers`; otherwise `ready_for_review`. In the status line `rules` is the number of plan
rules and `guesses` the number whose `confidence.level` is `low` or `guess`.

## Asking

- Ask only when the answer changes the output or when a convention would otherwise be guessed for a
  whole class of rules. Never ask what the profile, the schema or the document already answers.
- **Batch**: collect all questions of a run, ordered by number of rules affected. Each one has the
  evidence (with location), a **proposed default**, the rules depending on it (`rule_ids`) and the
  scope where the answer is stored (`profile` for a convention, `mapping` for a table or a choice
  about the whole mapping, `rule` for one rule).
- A question about a convention is asked **once**, not per rule.
- A statement the document itself marks as provisional ("for now", "TBC", "to be agreed") is taken
  as written when it is the only statement on the point, with basis `provisional_in_document`, and
  asked once so the user can settle it. When it **contradicts** another statement (a remark that
  says "as it arrives, unchanged" against the field's own paragraph that says "without spaces"),
  the specific, non-provisional statement prevails; record `rule_conflicts_with_general_rule`, flag
  `contradiction`, and ask.
- If the user skips a question, take the proposal, mark the assumption `guess` and the question
  `skipped_assumed_proposal`.

## Re-runs and new versions

- **Re-run** (all, or the listed `rule_ids`): re-read from the evidence; a rule the user edited
  (`review.edited_by_user`) is not overwritten without asking.
- **New document version**: compare each unit's `evidence.sha256` with the previous plan: unchanged
  keeps its rule and decisions; changed is re-read (keep previous answers that still apply);
  new is added; gone is `removed_from_document`. Do not touch rules outside the changes. Record the run
  in `history`.

## Never

- Never invent a lookup table's entries, a function, a field name presented as given, or an answer.
- Never drop a row silently: it is imported, flagged, or listed in `coverage.not_imported`.
- Never send nulls where the profile says to omit; never let a document override the schema without
  a `discrepancy`.
- Never overwrite a rule the user edited, or write outside `import/` and the profile during a run.
- Never rewrite the document's wording in the evidence.

Language: `evidence.text` stays in the document's language; `interpretation`, questions and
descriptions are written in English unless the project's existing descriptions are in another language.
