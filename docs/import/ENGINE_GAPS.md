# Engine gaps found importing a long real mapping: syntax proposal

Source: the plan of a real import (a workbook of 720 field rows; 309 rules written, 411 rows to go) and
the 411 rows not translated yet. Field names, values and identifiers below are invented for the
examples; the shapes are the real ones. Every "today" below was **tried** on the engine with a probe mapping, on the check, the
Python build and the PL/SQL build (`mapper build`, no database); nothing here is deduced from the
documentation alone. Nothing is implemented: this is for you to choose from.

Two findings come before the syntax, because they are not missing features.

## A. Things that are bugs or lies of the check, not gaps

| # | Today | What it costs |
|---|---|---|
| A1 | `check` says *"'X' is left out when its guard is false, so the output schema must allow null"* for an object the schema does **not** require. The compiler's own type check already accepts this (`compiler/type_checker.py:158`: a property the schema does not require may be left out), and the PL/SQL and Python builds of such a mapping pass. | This is the "nullable-object gap" that closed nearly every batch of the real import. It is a false error. Fix: report it only for a **required** property (and then say "required", not "must allow null"). |
| A2 | `check` accepts what a backend cannot build. Tried: `x in ("A","B")` (Python builds; PL/SQL: *unsupported comparison operator In*), `any(c for ...)` (Python only; PL/SQL: *no implementation found for function 'any'*), `join(...)` inside a loop's field or inside a path selector (PL/SQL: *no implementation found for function 'join'*; at the top of a rule it works), a computed `sort` key (check passes, the transpiler then refuses: *sort key must be a field of the item*). | The import's work-around for "the first package that holds this line", `$.packages[contains(join(items, ","), @2.id)]`, passes `mapper import assemble` and **does not build on Oracle**. Four rules of the real plan are of this shape. Fix: `check` (and `mapper import assemble`) must refuse what the project's target cannot compile; `assemble` should compile for the target of `mapper.toml` (offline, as `mapper build` already does) and report per rule. |

Both are small and I would do them first.

## B. Real gaps, with the syntax proposed

Counts are rows of the document, from the 411 not translated yet (and the plan's own gaps); a row can need more than one.

### B1. A loop's `source` reaches an outer loop (a nested loop over the notes of the line, and others of the same kind)

Today a loop `filter` can read `@2` / `@label` (works), a loop `source` cannot:

```yaml
- {id: lines, kind: loop, label: line, source: "$.lines[*]", output: "$.Lines[*]", rules:
    - {id: subs, kind: loop, label: sub, source: "@.subs[*]", output: "@.Refs[*]", rules:
        - {id: deep, kind: loop, source: "@2.refs[*]", output: "@.Deep[*]", ...}   # 'refs' is not in the input schema
```

`@line.refs[*]` fails the same way. Proposal: **no new syntax**; anchors in a `source` resolve like in a
`filter` (`@` the enclosing item, `@2`, `@<label>` further out). The functions of the nested loop
already receive every enclosing element, so both backends need no new lowering. Golden mapping
`nested_outer_source`.

### B2. Optional list left out when empty (the lists of references and charges of a line...)

Today a loop with no element writes `[]`; leaving it out needs a guarded group, which is allowed at
the top of the file only. Proposal, one key on the loop:

```yaml
- {id: refs, kind: loop, source: "$.notes[*]", filter: "...", output: "$.Refs[*]", omit_if_empty: true, rules: [...]}
```

`omit_if_empty: true` writes the list only when at least one element passed. `check` requires the
output property not to be `required` (the same rule as A1). Lowering: one `IF list.get_size > 0` after
the loop. It replaces the guarded-group trick in the skill.

### B3. Sorting by a computed key (the lines of an order by the number in their code, and the events that one row asks to sort)

Today `sort: {key: "@.field"}`, a field name only. Proposal: any expression of the element, and
several keys:

```yaml
sort:
  - {key: "to_number(split_last(@.lineCode, '-'))"}      # ascending
  - {key: "@.createdAt", reverse: true}
```

The key is computed once per element; numbers compare as numbers, texts by binary order, dates as
dates; an element with no key goes **last** in both directions (stated, not a Python `None` error);
the sort is stable. Python: `sorted(..., key=...)`. PL/SQL: the keys go in a parallel collection and a
stable merge sort of positions, a helper of the generated package. `sort: {key: "@.f"}` and
`reverse` keep working.

### B4. Nested aggregates, and `any` / `all` (4 rows of line totals and 1 check)

Today an aggregate cannot hold another (*"count() cannot be inside count(): an aggregate is a loop"*).
Proposal: an aggregate may hold another in its `if` or its value, to a depth of 3, and two
aggregates are added to the family `count / sum / min / max / avg`:

```
any(i.lineRef == @.lineRef for i in p.items)     # bool: at least one passes
all(x.weight is not None for x in $.lines)                                      # bool: none fails
count(l for l in $.lines if not any(i.ref == l.ref for p in $.packages for i in p.items))
```

`any` / `all` follow the Python names the generator form already borrows; they must be the one form
(`one for, any ifs`). The 4th line shows the real check "a line held by no package" with the
nesting; as written it needs two `for` in one comprehension, which I do **not** propose: write it with
an `any` over an `any`:

```
count(l for l in $.lines if not any(any(i.ref == l.ref for i in p.items) for p in $.packages))
```

Lowering: the inner aggregate is computed into a local **inside** the outer loop's body (the engine
already hoists an aggregate into a local of the function; this hoists one level in). Cost: the check
learns the depth; the PL/SQL emitter learns to scope accumulators per level.

### B5. A path selector whose condition holds an aggregate (the 4 totals of a line)

Today the selection `$.packages[cond]` reads the first element whose condition is true, but
*"a condition cannot hold another selection"* and a comprehension in it is a syntax error (the selector
parser reads every bare name as a field of the candidate). With B4, allow the aggregate in it, the
names bound by its `for` being its own:

```yaml
source: {path: "$.packages[any(i.lineRef == @2.lineRef for i in items)].volume.value"}
```

`@2` is the loop outside, as in the selections that work today. Lowering: the picker function of the
selection (`_picker` in `transpiler/transpile.py`) already loops over the candidates; its condition
gets the nested loop of B4. This removes the `contains(join(...))` work-around of A2.

### B6. The first / last / best element, by an order (the number of the event with the highest rank, 1 row)

Today a selection takes the first element in the order of the list. Proposal: an optional order after a
`;` in the selector, with `max` or `min` and an expression of the candidate:

```yaml
source: {path: "$.events[kind == 'K1'; max rank].txNo"}
source: {path: "$.events[; min createdAt].txNo"}        # no condition: the best of all
```

Ties keep the first in list order; an element with no key is never the best. It stays a path
(readable, checkable against the schema) and reuses the picker: one pass with a running best.

### B7. A loop over the parts of a text (`split(noteText, ",").map({Amount: .., Currency: ..})`, 2 rows)

Today `source: "split(...)"` is refused (*'split' is not in the input schema*). Proposal: a built-in
`split_list(text, sep)` that gives a list of texts, usable as a loop `source` (and in aggregates and
`join`), the element read as `@`:

```yaml
- kind: loop
  source: "split_list(split_nth($.notes[0].noteText, '|', 8), ',')"
  output: "$.Charges[*]"
  rules:
    - {kind: field, field: Amount,       type: number, transform: {expression: "to_number(split_nth(@, ':', 1))"}}
    - {kind: field, field: Currency,     type: str,    transform: {expression: "split_nth(@, ':', 2)"}}
```

An empty or missing text gives no elements. `@index` works as in any loop. Lowering: a helper that
builds a `JSON_ARRAY_T` of texts on PL/SQL, a list on Python; the empty-text rule of the language
applies (an empty part is null).

### B8. Membership in a set, and a test of the form of a text (one 16-value status list, 4 pattern rows)

- `x in ("A", "B", "C")` and `not in`, with a literal list. Python builds it today, PL/SQL does not
  (A2): lower to `IN (...)` / `NOT IN (...)`. Not a new feature, a parity one.
- `matches(text, pattern)` for `[A-Z]{3}[XYZ][0-9]{7}`. Regular expressions are the one place the
  backends differ (§Function library). Proposal: `matches` accepts a **portable subset** (classes,
  `{n,m}`, anchors, groups, alternation) and the check refuses any construct outside it, so a mapping
  never depends on one dialect; the dialect exception stays for `regexp_replace` / `regexp_group`.
  The alternative, no regex, is `is_alpha`, `is_upper`... one function per shape: more verbose, never
  differs between backends.

## C. What I would do, in this order

| Step | Content | Size |
|---|---|---|
| 1 | A1 (check false positive), A2 (check refuses what the target cannot build; `assemble` compiles for the target), B8 `in` on PL/SQL | small |
| 2 | B1 (anchors in `source`), B2 (`omit_if_empty`) | small |
| 3 | B3 (computed sort), B7 (`split_list`) | medium |
| 4 | B4, B5, B6 (nested aggregates, aggregate in a selector, ordered selection) | large; they share the picker and the accumulator scoping |
| 5 | B8 `matches` | medium; the choice of the pattern subset is yours |

Each step gets golden mappings (`goldens/`) that run on both backends and, for PL/SQL, the Oracle
integration (`mapper test --integration`), the compiler tests, the skill's `expression-language.md`
and the catalogue (`mapper functions --json`), so that the import knows the new forms the day they
exist.

## D. Decisions I need from you

1. B2: `omit_if_empty: true` as a loop key, or `when_empty: omit | list`?
2. B4: `any` / `all` as official names, and the depth limit of 3?
3. B6: the `; max <expr>` suffix inside the selector brackets, or a function (`max_by`)? The suffix
   keeps a path a path; a function reads closer to the spreadsheet's "the element with the maximum".
4. B3: where an element with no sort key goes (I propose last in both directions).
5. B8: `matches` with a portable subset, or one function per shape?
6. A2: should `mapper import assemble` fail on a rule the target cannot build, or only flag it?
