# Protocol between the skill and the wizard

The skill is provider-neutral (a Markdown prompt plus files). The wizard (desktop tool) detects the
installed assistants (Claude Code, Codex/ChatGPT CLI...), asks which to use if both are present, and
runs one in non-interactive mode with this skill as instructions. Nothing in the protocol depends on
the provider.

## One run
Input (the prompt the wizard builds): document path, project path, mapping id or "ask", profile name
or "ask", and the mode:

| mode | meaning |
|---|---|
| `import` | first run for this document (and mapping) |
| `resume` | continue after the user answered questions in `ir.json` |
| `rerun_all` | redo every rule from the evidence (edited rules are asked about) |
| `rerun_partial` | redo only the listed `rule_ids` |
| `revalue_version` | the document has a new version: compare hashes, redo what changed |
| `survey` | a long document: classify its units into `units.json`, translate nothing |
| `translate` | one batch of those units (`batch`), merged with `mapper import add` |

Files: as listed in `SKILL.md`. The wizard validates `ir.json` against `references/ir.schema.json` after
each run; an invalid file is a failed run.

## Final line
The last line on stdout is a single JSON object, nothing after it:

```json
{"status": "needs_answers", "ir": "import/<mapping>/ir.json", "open_questions": 3, "rules": 21, "guesses": 4}
```

`rules` is the number of plan rules, `guesses` the number at confidence `low` or `guess`.
`status` is one of `needs_answers`, `ready_for_review`, `failed` (then `error` says why). A run that
needs to know which mapping to import, before it has an IR, answers with `needs_answers` and writes a
minimal plan whose `questions` holds the choice (`scope: mapping`, `options` = the mappings found).

## Answers
The wizard writes `questions[i].answer` and sets `status: answered` (or `skipped_assumed_proposal`),
then starts a `resume` run. For `scope: profile` the skill copies the answer into the profile
(`basis: user_answer`, `confirmed: true`); the wizard does not edit the profile.

## What the wizard does itself (not the skill)
Detecting the provider, showing the plan, collecting answers, schema import, and applying the accepted rules to the project with
`mapper import apply <mapping>` (it re-checks the working copy, refuses to replace an existing
`mappings/functional/<mapping>.fn.yaml` without `--force`, and marks the rules `applied`). The
skill never applies rules. Commands, all run from the project directory, all printing one JSON
object: `mapper import extract`, `assemble`, `test`, `apply`.

## Long documents
Above about 80 units (or when `units.json` already exists) the wizard does not start one run but a
`survey`, then `translate` runs, up to two at a time (`docs/import/BATCHES.md`). The survey's final
status is `ready_for_review` when it classified the units (the wizard reads that as "surveyed" and
goes on, with the questions it asked still open) or `needs_answers` when it could not. A worker never
writes `ir.json`: it hands rules to `mapper import add`, asks with `mapper import ask`, and reads
answers with `mapper import answers`. The wizard shows the open questions while the batches run, and
queues the rules an answer touches (`rule_ids`) for another pass. Commands: `mapper import queue`,
`batch`, `add`, `ask`, `answers`, `gaps`, and the views of the extracted document (`outline`, `rows`,
`blocks`, `find`).
