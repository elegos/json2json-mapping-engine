# Writing rules: the shape of a `.fn.yaml` and its expressions

What follows is the **syntax** only. Which functions exist is never listed here: it comes from
`mapper functions --json` at the start of every run. Source of truth: `docs/ARCHITECTURE.md`
(§Rule format, §Scope anchors, §Expression language, §Selecting one element). Each statement
below was checked against the transpiler; if `mapper fn check` disagrees, the check wins.

## File skeleton

```yaml
name: "Meter report"
id: meter_report
rules:
  - id: report
    kind: object            # an output root: its rules write inside it
    output: report
    rules:
      - id: site
        kind: field
        field: site         # a name, never a path ($.report.site is rejected)
        type: str           # str | int | number | bool | date
        source: {path: "$.readings.site.code"}
        transform: {expression: 'concat($.readings.site.code, " / ", $.readings.site.name)'}
        description: "..."
        validation: {needs_review: true}
  - id: loop_orders
    kind: loop              # one output element per source element
    label: order
    source: $.shipment.orders[*]
    filter: "not is_empty(@.weightKg)"
    output: $.notices[*]
    rules: [ ... ]
```

- A top-level output (a root object, or fields written straight into the output root) needs the
  right wrapper: an `object` rule with `output:` for a named root, a `loop` for an array.
- `required: false` makes a field optional (omitted when its value is missing).
- Inside an `object`, a loop's `output:` is relative to it (`lines[*]`, not `$.note.lines[*]`);
  `mapper import assemble` reports a wrong one.
- **Alternative shapes** (the output schema is a `oneOf`): a group, `kind: object` with
  `output: $` and a `guard`, whose rules write into the output root, all or none:

  ```yaml
  - {id: post, kind: object, output: $, guard: "$.operation == 'POST'", rules: [ ... ]}
  - {id: delete, kind: object, output: $, guard: "$.operation == 'DELETE'", rules: [ ... ]}
  ```

  A list written inside a group (a `loop`) exists in the output only when the group's guard
  holds: a message the guard excludes gets neither the fields nor the empty list.

  In the plan a group is a rule with `intent: structure`, `target.path: $`, and the group's
  evidence (the band, sheet or section that opens the shape) in `evidence`; it is not a unit of
  the coverage count, and its id is `<group id>@<location>` like any other.

  Groups are at the top of the file and run in order; the guards are the author's to write and
  must exclude one another (nothing checks it, a test case that matches two shows it).
- **Ordering a list**: `order_by: "<expression> [asc|desc] [nulls first|last], ..."` on the loop, SQL's
  `order by`: `order_by: "to_number(split_last(@.lineCode, '-')), @.createdAt desc"`. A key that is not a
  plain field of the element must produce a number or a text the language knows (`to_number(...)`,
  `to_string(...)`, `upper(...)`, arithmetic), not an `if_else` of fields: wrap it. An element with
  no key goes last unless `nulls first`. Equal keys keep the source order. There is no `sort:` to
  write any more.
- **The best of several**: a selection reads the first match; to read the one with the highest or
  lowest of something, say it as in SQL: `$.events[kind == 'K1' order by to_number(rank) desc].txNo`
  (same clause and same rules for the key's type as a loop's `order_by`).
- **A loop over the parts of a text** ("for each value of the comma-separated list, one entry"):
  `source: "split_list(split_nth($.notes[0].noteText, '|', 8), ',')"`; the element is a text, read as
  `@`: `split_nth(@, ':', 1)`. An empty part is a null element: `filter: "not is_empty(@)"` leaves it
  out. A missing or empty text gives no element.
- A loop's `source` may start from an outer loop, as a `filter` may: `@2.refs[*]` or `@line.refs[*]`
  (`@` is the loop it sits in, `@2` the one outside it).
- **An optional list left out when empty**: `when_empty: omit` on the loop (`list` writes `[]`). Unset,
  the list is left out unless the output schema requires it: do not wrap a loop in a guarded object
  for that. `omit` on a required list is refused by the check.
- An output list with **one element built from the whole message** (a wrapper such as `entries`
  holding a single `content`): a `loop` with `source: $` (the document is its one element) and
  `output: entries[*]`; its fields read the message as `@.field`. The same loop with a `filter`
  is a block written only when a condition on the message holds ("emitted only if ...").
- Several blocks adding to **one list** (sections that each add notes to `items`): one `loop` per
  block, all with the same `output: items[*]`; the elements come out in the order of the rules.
  A loop runs over a list, or over `$`; a path to an object is refused by the check.
- A numbered line ("running number from 1"): `index_start: 1` on the loop and a field with
  `source: {path: "@index"}` and no expression (an expression such as `@index + 1` also works).
- A lookup is a top-level rule `kind: lookup` (`label`, `type`, `entries`); read it as
  `lookup(key, @LABEL, default)`. `mapper import assemble` writes it from the plan's `lookups`
  (status `in_document`, `provided`, `partial` or `missing`); a table the document does not give is written
  empty, with the entries there are, so that rules can already read it.
- A function's result type must fit the field: `abs` of a whole number is a whole number (and so
  is a `sum` of them), `floor` and `ceil` give whole numbers, `round` and the other arithmetic give
  `number`. An integer field takes a whole-number expression (`type: int`); `number` does not fit
  it. When the document wants a whole number from a computation that gives `number` (a weight in
  grams from `kg * 1000`), make it whole with `floor` or `ceil`; for "rounded to the unit" of a
  value that is never negative, `floor(x + 0.5)`. Never change the field's `type` to fit the
  expression, and never leave a rule that does not pass: if no whole-number form says what the
  document says, flag a discrepancy with the output schema and keep the rule a flagged guess.
- A field's `field` is a name, never a path (`occurredAt.value` is not one). A target written as a
  path (`occurredAt.value`, `student.id`) is an `object` rule (`output: occurredAt`) holding a
  field rule (`field: value`); an `object` rule has its own plan rule (`intent: structure`).

## Paths and anchors

- `$` is the document root; `@` the current item of the nearest loop (`@2` the next one out,
  `@<label>` by label); `@index` its position (0-based).
- In an expression, `value` is the rule's own Source.
- A **loop's `source:`** takes `[*]`. An **expression** does not: write the array path plainly
  (`sum($.samples, 'value')`; `$.samples[*]` is a syntax error there).
- Source paths are spelled from the real root of the input schema: a document that says
  `source.readings.unit` and a schema rooted at `readings` is `$.readings.unit`.

## Positions, constants and lookups

- Positions: array elements `[n]` count from 0, but `substring` and `split_nth` count from 1, and
  `@index` follows the loop's `index_start`. A document that counts from 1 everywhere ("the 3rd
  part", `Fines[1]` is the first) needs `+ 1` / `- 1` where it meets the other base: state the
  base in the profile and apply it in every rule.
- A constant field has no source: `transform: {expression: '"LQ.STOCK"'}` (quote the text inside
  the YAML string) or a number; it needs no `source`.
- `lookup` is an exact match. A document that says the lookup is case-insensitive is read by
  writing the keys of the table in lower case (they are the document's entries, normalised: say
  so in the assumptions) and looking up `lower(key)`.

## Values

- Missing/absent is `None`; booleans `True` / `False`; `null` and `true` are not names here.
- Text in quotes, either kind. Operators `+ - * /` and `== != < > <= >=`, `and or not`.
- **A text that must have a shape**: `matches(text, "[A-Z]{3}[XYZ][0-9]{7}")` is true when the whole text
  fits (null for a missing one). The pattern is a literal in a portable subset: characters, `.`, `[a-z]`,
  `[^0-9]`, groups, `|`, `* + ? {n,m}`; no `^` or `$`, no `\d \w \s \b`, no `(?...)`. Say the digits as
  `[0-9]`, not `\d`. This is not `regexp_group` (which keeps the dialect of the backend).
- Membership in a literal list: `x in ("A", "B")` and `x not in (...)` (all texts or all
  numbers; a missing `x` is in nothing). The list must be written out: `x in $.allowed` is not supported.
- An empty text counts as null everywhere (never written to the output).
- `concat` leaves the separators where they are when a part is missing: `concat(a, "-", b, "-", c)`
  with `a` and `b` missing is `--C`. That is the language, not a question for the user; a document
  that drops the separator of a missing part is written with `if_else` on each part.
- Local names inside a multi-line expression: `x = ...` lines, the last line is the value.

## Two things that look like filters and are not

1. `$.items[marker = 'A']` in a path **selects the first matching element** (and gives nothing
   when none matches). It is not a filtered list. Never write `count($.samples[quality = 'OK'])`
   or `sum($.samples[quality = 'OK'], 'value')`: they read one element, not the matching ones, and
   `mapper fn check` still accepts them.
2. A loop's `filter` keeps or skips whole elements of that loop.

So "count / sum / max of the elements that satisfy a condition" is written as an aggregate over a
comprehension (next section), never with `[cond]` in the path.

## Aggregates

Over a whole list: `count(list)`, `sum(list, 'field')`, `min`, `max`, `avg` (`field` is a name in
quotes).

Over the elements that satisfy a condition, or over a value computed for each element, write the
Python form with a single `for` and any number of `if`s:

```
count(s for s in $.samples if s.quality == 'OK')
sum(s.value for s in $.samples if s.quality == 'OK' and s.value > 10)
max(abs(s.value) for s in $.samples if s.quality == 'OK')
sum(abs(l.quantity) for l in $.lines)
```

`s` is a name of your choice for one element; its fields are read as `s.field` and are checked
against the schema. Only `count`, `sum`, `max`, `min`, `avg`, `any` and `all` take this form. One may
stand in the condition or the value of another, to any depth (each level runs a loop inside the one
outside it): `count(l for l in $.lines if not any(any(i.ref == l.ref for i in p.items) for p in
$.packages))`. `any(cond for x in list)` is true when one element passes, `all(...)` when every element
does (an empty list: false and true); a missing value is false.
`count` counts the elements that pass (its value is not looked at); the others skip an element whose
value is missing. There is no `[*]` in the path.

`join` writes the texts of a list in one text: `join($.tags, ", ")`, or over a comprehension, which
goes in parentheses because the separator follows it: `join((to_string(i.id) for i in $.items if
i.ok), ", ")`.

An aggregate may be part of a larger expression: `round(sum(...), 2)`, `count(...) + 1`.

An empty list (or a list where nothing passes): `sum` and `count` are 0; `min`, `max` and `avg` have
no value, so the rule is not written. State what the document wants for the empty case, and check
it against these.

## Field names

A field may have any name, including a Python keyword (`$.return.number`, `i.from`): write it as
it is. Do not write `$["return"]`: `[...]` after a path is the "first matching element" selector.

## Omitting a field, or writing null

The rule of the language: a value of `None` (nothing to write: a missing source, a lookup that finds
nothing, `max` of an empty set) leaves the **field out**. `Null`, the explicit
null (a keyword, not a Python `None`), writes the field with the value `null`. Use `Null` only when
the document asks for a null to be sent ("send null", "empty value `null`"); "not sent", "omitted",
"left blank" mean `None`.

```
max(s.value for s in $.samples)          # nothing when the set is empty: the field is left out
if_else(is_empty($.a), Null, $.a)        # writes "a": null when a is empty
```

Inside an `object` or a `loop` (where nearly every field lives) an expression is assignments
followed by one value: no `if` or `return` statement there. Write the omission, or the null, as a
value: `if_else(cond, None, x)` leaves the field out, `if_else(cond, Null, x)` writes `null`
(both verified in an `object`). A bare `return` is only for a field written straight at the top of
the file.

Both branches of `if_else` are always evaluated, so a division inside it
(`if_else(n > 0, t / n, None)`) still fails when `n` is 0. Guard the divisor instead:

```
n = count(s for s in $.samples if s.quality == 'OK')
if_else(n == 0, None, round(sum(s.value for s in $.samples if s.quality == 'OK') / if_else(n == 0, 1, n), 2))
```

A field that can be left out needs `required: false` in its `fn_rule` (the default is required);
write it for every field the schema does not require, and for any rule that can give `None`.

A property the schema **requires** cannot be left out: a rule that can give `None` for it fails the
compiler's type check (`mapper import test` reports the cases as not run, "does not compile").
Report that as a discrepancy against the schema; do not change the schema.

## Validations: refusing or flagging a message

A statement such as "reject the message if the VAT number is not 11 digits" is not a rule: it is a
check of the message (`validations:` of the file, the plan's `validations` array). In the file:

```yaml
validations:
  input:                      # before any rule runs; `output:` checks the result after the last
    schema: false             # true: also validate against the mapping's JSON Schema (off by default)
    checks:
      - id: vat_format
        expect: "not $.vatId or (is_digits($.vatId) and length($.vatId) == 11)"
        code: REQ-16          # reported when it fails
        message: "The VAT number must have 11 digits"
        action: reject        # reject (no output at all) | warn (reported only)
```

- `expect` is a condition on `$` (the checked document: the message for `input`, the result for
  `output`) and must be **true**. A comparison with a missing value is not true, so say what a
  missing value means: `not $.vatId or ...` for an optional field, `$.vatId` for a mandatory one.
- All failed checks are reported together; they never stop each other. A rejected message runs no
  rule and has no output. A loop that has to skip an element is a `filter`, not a validation.
- `is_digits(text)` is true when the text is made of the digits 0-9 only (and not empty).
- `schema: true` is best effort: the database validator does not look at a `format` (a `date-time`
  text is checked to be a text). The checks are the way to be exact.

## Named sets used by several rules (`good := ...`)

A document that names an intermediate set and reuses it has no local variable to map to across
rules. Do not copy the definition silently into each rule. Record the definition as
`inherited_context` (kind `other`) of the rules that use it. When it is a filtered list that
rules only count or add up, each of those rules writes the filter itself in its aggregate (see
above); a filtered list that a rule must output element by element is a function gap.

## Nothing else is syntax you may invent

Lambdas, comprehensions outside an aggregate, method calls (`x.upper()`), `[a:b]` slices and string formatting are not
available in the functional dialect. Use catalogue functions (`upper`, `substring`, `left`,
`format_date`... when `mapper functions` lists them); patterns (`regexp_*`) are the last resort,
because they cost more to run and differ between backends.
