# Import plan (IR) — design notes

The import of a functional document does not write `.fn.yaml` directly. It first produces an
**import plan** (the IR, `skills/import-functional-spec/references/ir.schema.json`), which the wizard shows, the user corrects, and from
which the project's rules are generated. The plan is a project artifact: it can be compared,
re-run (all or part of it) and re-evaluated for a new version of the document.

Two examples validate against the schema: `examples/wb1_excerpt.ir.json` (a spreadsheet with
schemas) and `examples/prose_no_schema.ir.json` (one prose sentence, no schema at all).

## Principles

1. **Nothing is style-specific.** The plan has no field for "family A". What differs between
   documents (index base, array notation, null rule, date dialect, meaning of colours, scope of
   conditions...) is a **convention**, stored in a *profile*, or a **question** when the evidence
   is thin. The fixtures in `tests/fixtures/import/` are calibration examples, not the list of
   supported styles.
2. **Every rule keeps its evidence.** `evidence.text` is verbatim and `sha256` covers it plus the
   inherited context (band title, loop, root path). Re-evaluation for a new document version is
   a comparison of hashes: unchanged rules stay, changed ones are re-read, new ones are added,
   missing ones are marked `removed_from_document`.
3. **Interpretation before code.** `interpretation` states the rule in plain words, with
   `assumptions` each tagged by `basis` (`profile`, `document_evidence`, `user_answer`, `guess`).
   `proposal.fn_rule` is derived from it. `back_translation` restates the generated rule from the
   proposal alone, so a drift between the two is visible.
4. **Doubt is data, not text.** `confidence.level` + `flags` + `questions` + `discrepancies`.
   A guess is allowed (and required, when there is nothing else) but is labelled `guess` and its
   `description` in the project says so, with the original wording.
5. **No invention.** A missing lookup stays empty with a flag (never made-up entries); a missing
   function becomes `functions_missing` (never an invented name); a field not in the schema is
   `in_schema: false` with a did-you-mean.
6. **Without a JSON Schema** (`schemas.*.origin = none`) paths cannot be verified: confidence is
   capped at `guess`, paths come from the wording, and the wizard offers to *infer* a schema
   (`origin: inferred`) that the user must confirm. After confirmation the plan is re-checked.

7. **A rejection is not a rule.** A statement that refuses or flags a message ("reject if the VAT
   number is not 11 digits") goes in `validations` (side, `expect`, `code`, `message`, `action`),
   with the same evidence, interpretation, confidence and review as a rule, and becomes the
   `validations:` section of the file; `schema_validation` says whether each side is also checked
   against its JSON Schema (off unless asked). A case whose message the document says is refused
   states `expected_rejected` (the codes) instead of `expected`.

## Where the answers live

| `question.scope` | Stored in | Effect |
|---|---|---|
| `profile` | the profile (a project file, reused by other mappings that pick it) | convention, asked once |
| `mapping` | this plan | e.g. content of a missing lookup |
| `rule` | the rule | one-off choice |

When a new mapping is imported the wizard offers the existing profiles (e.g. the one of
`orders`, `shipments`, `consignments`, or that of `service_invoices`) or a new one. A reused
profile is still checked against the new document and divergences become questions.

## Runs

`history[]` records each run. A partial run lists the `rule_ids` it touched. A rule the user
edited by hand (`review.edited_by_user`) is never overwritten without asking. Document version:
file name, version sheet and column are all recorded in `document.version.candidates`; if they
disagree the user decides which prevails; if none is declared the plan takes `1.0`
(`origin: assumed_default`).

## What the plan depends on, from the engine

- **Function catalogue** — the `functions` op of `mapper serve` (`cli/functions.py`) already lists
  built-ins and project functions with signature and doc. The skill reads it at run time;
  nothing is copied into the skill. `mapper functions [--json]` prints the same list from the
  project directory (text for people, `{"ok", "functions": [...]}` for the skill).
- **Check** — `proposal.check` is the result of the existing check on the generated rule.
- **Validations** — `validations[].check` is the result of the check on the generated check
  (`expect` read against the input or the output schema); `mapper import test` runs the cases that
  expect a rejection.
- **Rule format** — `proposal.fn_rule` follows the functional file schema in
  `docs/ARCHITECTURE.md`; `validation.needs_review` is set for anything not `high`.

## Relation to the earlier design

`docs/ARCHITECTURE.md` (§Migration from existing mapping files) describes a column mapping saved
as an `.import.yaml` "import profile" and a row-by-row LLM translation. That fits a document that
is a regular table. This plan generalises it: the *profile* here holds conventions (not column
positions), a table is one of several shapes the reader can normalise, and the stage between
reading and generating is reviewable. The ARCHITECTURE section should be rewritten when the
profile format is fixed.

## The skill

The procedure that produces the plan is `skills/import-functional-spec/` (`SKILL.md`, with the
checklist of conventions, the run protocol with the wizard, and the schemas of the plan, the profile
and the normalized document that the extractors hand over). The extractors (xlsx, docx, pdf,
txt, md -> normalized document) are `cli/docread/`, run with `mapper import extract` (optional
libraries: `uv sync --extra import`; PDF has no table reconstruction and no OCR). The commands that apply a plan are `mapper import assemble | test | apply` (`cli/import_plan.py`).

## The wizard (desktop tool)

The *Import a document…* screen (`ImportView.tsx`, opened from the start wizard) is full screen, can
always be closed, and a run can always be cancelled. Steps: **Document** (file, assistant, profile,
mapping; the imports already in the project, to continue, redo or read a new version of the
document), **Run** (progress of the assistant), **Questions** (one card per question, the ones that
touch most rules first; options, the proposal, a free answer, or "assume the proposal"),
**Review** (summary; rules as a list and a detail with the evidence, interpretation, assumptions,
proposed rule, check result and a note to ask again; validations; lookups; cases; discrepancies;
coverage; schemas and profile) and **Apply** (what goes in, what is left, `--force` only when asked).

- *Run.* `mapper import run` (`cli/import_run.py`) detects Claude Code and Codex on the PATH
  (`mapper import providers`), puts a copy of the document in `import/documents/` when it lives outside the project (the
  assistant reads only inside the project and the skill's folder, writes only `import/**` and may
  run only `mapper`), builds the prompt, starts the assistant non-interactively and prints one JSON
  line per event; the last has `event: done` and the protocol's status. The desktop tool starts it
  as a process of its own (`import_run_start`, events `import-line` / `import-exit`) and cancels it by closing its
  stdin: it is long, and the worker `mapper serve` answers one request at a time. When it ends the
  wizard validates `ir.json` against the schema (a plan that does not conform is kept as
  `ir.invalid.json` and the previous plan is put back), computes `document.sha256` and
  `profile.sha256` itself and appends the run to `history`.
- *Operations on the plan* are ops of `mapper serve` (`cli/import_ops.py`): `import_list`, `import_plan`,
  `import_answer` (`questions[].answer`, `status`), `import_review` (`accepted` / `rejected` / `pending`),
  `import_note` (a remark on a rule: a question of scope `rule`, topic `user_note`, already answered, and
  `review.note`; the next run `rerun_partial` reads it), and `import_test` / `import_apply`.
- *State of an import* (`cli/import_ops.py::state_of`): `needs_answers` (an open question),
  `answered` (answers given after the last run, which has not read them), `ready_for_review`, `applied`.
  A document or profile whose hash is not the plan's marks it stale.
- *Not in this version:* editing a rule inside the wizard (reject, ask again with a note, or edit the
  applied rule in the grid), turning the plan's cases into golden cases, and the Codex command line
  (written from its documentation, never run).
- *Headless check:* `node desktop/ui/shots/import-check.mjs` walks the whole flow with a stand-in
  for the assistant (`J2JME_IMPORT_PROVIDER`, `shots/fake_provider.py`).
