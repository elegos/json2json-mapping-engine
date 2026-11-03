# Import profile — design notes

A **profile** records how the functional documents of one group are read. It holds conventions,
not column positions and not a style name: the reader does not need to know that a document is
"like" another one, only what its conventions are. Schema: `skills/import-functional-spec/references/profile.schema.json`; example:
`examples/wb1.profile.yaml`.

## What it is

- A project file (`import/profiles/<name>.profile.yaml`), committed with the project, readable and
  editable by hand. Its scope is the project.
- Linked to the mappings it serves (`applies_to`). A mapping picks, when imported: reuse a profile
  (e.g. the one of `orders`, `shipments`, `consignments`), reuse another (`service_invoices`), or
  start a new one. "Reuse with changes" makes a copy (`derived_from`).
- A list of **conventions**: `topic` + optional `context` + `value`, with `basis`, `evidence`,
  `confirmed`. Same topic in different contexts is normal (`index_base` is 0 in `code`, 1 in
  `prose`).
- Plus `layout`: where the rules are (one row per target field, paragraphs, bands...), what each
  column means. It is a hint to save re-discovery, not a template: if the next document does not
  fit, the reader says so and asks.

## Open-ended on purpose

Topic and value are free strings/structures. The topics below are the ones the reader *looks for*
and asks about when the evidence is thin; a document with a convention nobody listed produces a
new topic (and a question) rather than a failure. Nothing in the engine switches on a style.

| Topic (examples) | What it settles |
|---|---|
| `index_base`, `array_notation` | `[0]` / `[1]`, `[]` / `[*]` / no brackets, "first", "each" |
| `path_separator`, `root_path`, `name_case`, `functional_vs_technical_names` | how paths and names are written |
| `null_rule` | null / empty / absent, and what is sent when a mandatory value is missing |
| `mandatory_vocabulary` | `Y/N`, `M/O/C`... (an undefined letter becomes a question) |
| `condition_scope`, `section_semantics` | does a condition bind the row, the section or the message |
| `concatenation_operators`, `optional_part_separators` | `||`, `+`, what happens to a separator when a part is empty |
| `date_dialect`, `timezone_rule`, `number_format` | token set, source vs target, UTC, decimal separator |
| `delimiter_side` | "before / after the second delimiter" with a repeated delimiter |
| `lookup_not_found`, `lookup_location` | default for an unknown key; where the table lives |
| `marker_meaning` (context = the marker) | fill, strike-through, colour: meaning, or `unknown` |
| `removed_marker` | how a field dropped from the target is shown |
| `version_precedence` | which of file name / version sheet / column prevails |
| `review_dialogue` | how questions and answers are written in cells; whose word prevails |

## How it is used

1. **Choosing**: the wizard shows the profiles of the project with their `description` and the
   mappings they serve; a new profile starts empty.
2. **Checking a reused profile**: the reader tests each convention against the new document.
   A convention contradicted by the evidence, or a document feature the profile does not cover,
   becomes a `question` with scope `profile` (answer stored here) — never a silent override.
3. **Learning**: answers (`user_answer`, `confirmed: true`) and evidence-based findings
   (`document_evidence`) are added; `inferred` and `default` conventions are `confirmed: false`
   and every rule that depends on one carries an assumption with `basis: profile` + a flag until
   someone confirms. `exceptions` lists known deviations in the documents.
4. **Staleness**: the plan stores the profile's hash; a profile changed after a plan was made
   marks the plan stale (the rules depending on the changed topics are re-read, the rest stay).

## Out of scope for the profile

Per-rule decisions (they live on the rule in the plan), lookup contents (plan: `lookups`), the
document's own version (plan: `document.version`), and anything about a specific field.

## Relation to the fixtures

The `*.profile.json` files in `tests/fixtures/import/` are the **expected** conventions of each
synthetic document, written before this format existed. They will be converted to this format and
used as the expected result when testing what the reader discovers.
