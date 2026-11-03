# WB8 - Truth file: PDF, pseudo-code rules (close to our own language), schemas supplied as files

`MeterReport_mapping_v0.9.pdf` was produced from a Word file (text is extractable). Layout hazards on purpose: a running header and
footer on every page (noise to strip), a page break in the middle of the rules, footnotes `(1)`-`(4)` after the block they qualify,
two assignment spellings (`:=` and `=`), the filter written `[cond]` and `where cond`, a comment style `--`. Version: `v0.9` in the
file name and header (no other source). Schemas are **provided** (not in the PDF) -> `origin: provided`.

| Rule | Correct reading | Difficulty |
|---|---|---|
| meter | `upper(meterId)` | - |
| site | `code + " / " + name` | quotes in the PDF may render as typographic quotes. |
| unit | `unit`, default `"kWh"` when absent/null/empty | footnote (1) defines "empty". |
| periodStart / periodEnd | min / max of `ts` over **all** samples | comment says "whatever the quality", unlike the section 3 default; omitted without samples (footnote 2). |
| `good` | samples with `quality == "OK"` | an intermediate named set used by the next rules; `EST` is not good (section 4, open point). |
| count | `count(good)` | - |
| total | `round(sum(good.value), 3)`, half up; 0 for no good samples | - |
| average | `round(total / count, 2)` using the **rounded** total; omitted when `count == 0` | `=` instead of `:=`; the omission rule is in footnote (3), on the page after. |
| maxValue | `max(good.value)`; omitted when `good` is empty | - |
| qualityIssues | number of samples with `quality != "OK"` (all non-OK, `EST` and `BAD`) | `where` spelling of the filter. |
| firstSample | `samples[0].value`, **0-based** (declared in the intro), no quality filter; omitted if no samples | footnote (4). |

Tests: case1 (quality mix, out-of-order timestamps: `periodStart` is the min, not the first), case2 (null unit -> `kWh`, half-up
`1.005 -> 1.005` total and average `1.01`), case3 (no good samples -> `count 0`, `total 0`, no average/maxValue), case4 (empty samples).
