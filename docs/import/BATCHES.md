# Importing a long document: survey, batches, live questions

A document of a few dozen rules is read in one run (`SKILL.md`). One of 700 rows is not: a run
that rewrites the whole plan for every 30 rows is slow, fragile (a plan of 900 KB that fails the
schema is lost) and asks the same things again. This is the method for long documents. It is
generic: nothing in it knows a mapping; the assistant classifies, the code does the bookkeeping.

## Phases

```
survey (one assistant run)  ->  queue (code)  ->  translate (many runs, in parallel)  ->  review
        units.json                  queue.json         batches, merged by `import add`
        questions asked up front                       questions asked live
```

1. **Survey.** The assistant reads the document in slices (`mapper import outline|rows|find`), does
   what the first run does today (version, mapping, profile, schemas, conventions) and **classifies
   every unit**, writing `import/<mapping>/units.json`. It translates nothing. The questions it can
   already see (a convention, a root path, a scope) are asked now, once, by `mapper import ask`.
2. **Queue.** `mapper import queue <mapping>` validates `units.json`, takes the units the plan does
   not cover yet, handles the mechanical ones by itself and cuts the rest into batches of units that
   belong together (same group, then neighbours), into `queue.json`.
3. **Translate.** One assistant run per batch, several at a time. Each run reads the answers given
   so far (`mapper import answers`), translates its units, and hands the result to
   `mapper import add`, which checks it and merges it. A run never writes `ir.json`.
4. **Settle.** Answers that arrive after a rule was written queue a partial re-run of the rules
   they touch (`rule_ids`); when the queue is empty the plan is `ready_for_review` (or
   `needs_answers`).

## `units.json`

```json
{
  "units": [
    {"id": "Mapping!A6", "location": {"sheet": "Mapping", "cells": "A6:I6"},
     "target": "$.channel",
     "class": "constant", "value": "WEB"},
    {"id": "Mapping!A3", "location": {...}, "class": "skip",
     "reason": "other", "detail": "the logic column says not to map"},
    {"id": "Mapping!A12", "location": {...}, "target": "$.Items[*]", "class": "structure"},
    {"id": "Mapping!A40", "location": {...}, "target": "$.X.Y", "class": "copy", "source": "$.x.y"},
    {"id": "Mapping!A41", "location": {...}, "target": "...", "class": "translate",
     "group": "part_split", "needs": ["a loop that reads the line it belongs to"]}
  ],
  "groups": [{"id": "part_split", "description": "split(text, '|')[N] and a mapping of the part"}]
}
```

- `class`: `skip` (not a rule: `reason` is a `coverage.not_imported` reason), `structure` (an
  `object` / `loop` the document only implies), `constant` (`value`), `copy` (`source`), `translate`
  (a rule the assistant writes), `ask` (cannot be classified without an answer: `question` names it).
- The code turns `skip`, `structure`, `constant` and `copy` into plan rules and coverage entries
  (high confidence, `proposal.check` from `assemble`); the assistant is not asked again.
- `group`: units that read as one pattern. They go to the same batch, so the pattern is read once
  and the rules agree; the review can accept a group together.
- `needs`: for a `translate` unit, what the assistant expects the engine to lack, in a few words.
  `mapper import gaps <mapping>` counts them: the engine's gaps, known before a single rule is
  written, with the rows that wait for each.

A plan that already has rules (an import in progress) is surveyed **incrementally**: the units the
plan covers (by the location in the rule id, or by `coverage`) are not classified again.

## Commands (all print one JSON object)

| command | does |
|---|---|
| `mapper import queue <m> [--size N]` | units -> mechanical rules + `queue.json` |
| `mapper import add <m> <batch.json> [--batch ID]` | validates a batch of rules (and validations, lookups, discrepancies, tests), fills `evidence` from the document by location, checks it with `assemble`, merges it into the plan, marks the batch done. A batch that does not validate changes nothing and returns the errors |
| `mapper import ask <m> --text ... [--topic --scope --option --proposal --rules ...]` | adds a question; an equivalent one (same topic and text once normalised) returns the existing id, answered or not |
| `mapper import answers <m> [--rule ID]` | the answers given so far, each with its `rule_ids` |
| `mapper import gaps <m>` | `needs` of the units, counted, and the function gaps already in the plan |
| `mapper import drive <m> --document ...` | the orchestrator: survey, queue, workers, settle; JSON events on stdout |

`add`, `ask` and the answers written by the desktop tool read-modify-write `ir.json` under a lock
file, so that parallel runs and the user never overwrite each other.

## Live questions

A question is in `ir.json` from the moment `ask` writes it. The desktop tool polls the plan during
a run and shows the open questions as a backlog next to the log; answering writes the answer
under the same lock. The workers do not wait: a rule that depends on an open question is written
with the proposal as an assumption (`guess`), and when the answer comes the rule is queued for a
partial re-run. `ask` deduplicates, and the survey asks what it can foresee, so the same question is
rarely asked twice.

## Parallel runs

`drive` starts up to `--concurrency` (default 2) assistant runs, one batch each. They share nothing
but the plan, through `add` and `ask`. The profile is frozen after the survey (a worker that finds
a new convention asks, it does not edit the profile).
