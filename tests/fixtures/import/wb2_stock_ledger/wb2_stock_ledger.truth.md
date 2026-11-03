# WB2 - Truth file (style B): stock movements -> inventory ledger entry

Workbook: `StockMovement_to_Ledger_Mapping_v0.3.xlsx` (sheets `Version`, `Mapping`, `Validations`).
Schemas: `wb2_stock_ledger.input.schema.json`, `wb2_stock_ledger.output.schema.json`. Tests: `tests/case1..3`.

## 0. Global conventions (resolved)

| Topic | Correct reading |
|---|---|
| Colours / legend | Light blue = constant, light green = derived/concatenated, cream = optional, white = standard. Colour is **informative only**; where a row is both optional and derived the author's fill wins and the *rule text* is authoritative. |
| Index base | Code-like `reasons[0]` = **0-based**, first element. No prose indices in this workbook. |
| `[]`, `[*]`, `[kind=='DN']` | `[]` and `[*]` = every element; `[x=='v']` = filter. `reasons[0]` = first only. |
| Null / empty / absent | Equivalent. Optional target fields without a value are **omitted**; output never has `null`. |
| Mandatory column | `Y` and `Yes` = mandatory, `N` and `No` = optional (mixed vocabulary, same meaning). |
| Date dialect | `yyyy-MM-dd'T'HH:mm:ss.SSSXXX` (Java-like): always three millisecond digits, offset printed as `+HH:mm`/`-HH:mm`, or `Z` for zero offset. |
| Version | Authoritative version of the document = the one with highest number in sheet `Version` that is *approved*: see section 3. |
| Lookup `uomlist` | Not in the workbook. Correct content: `PCS -> EA`, `KGM -> KG`, `LTR -> L`. **Key not found => pass the source value through unchanged** (there is no default in the document; this is the chosen resolution). |
| Output envelope | `senderId`, `queueId`, `priority`, `keepOrder`, `haltOnFailure` at top level; everything under `body`. |

## 1. Rules (row numbers = order in sheet `Mapping`, header band first)

| # | Target | Correct interpretation | Assumptions / deliberate ambiguity -> resolution |
|---|---|---|---|
| 1 | `senderId` | `"LDG-" + movement.id`. | Column "Transformation Type" says *System Generated* but the rule is a deterministic concatenation: **the rule wins**, nothing is random. |
| 2-5 | `queueId`, `priority`, `keepOrder`, `haltOnFailure` | Constants `"LQ.STOCK"`, `0`, `true`, `false` (JSON number/booleans). | `Yes` in row 4 = mandatory. |
| 6-7 | `domain`, `entryLevel` | Constants `"W"`, `"ITEM"`. | - |
| 8 | `entryCode` | `"W." + type`, plus `"-" + reasons[0].code` only if the first reason has a code. | **Ambiguity:** optional part, no separator rule. Resolution: dash dropped with it (`W.RECEIPT`). **Sample value contradicts the rule** (`W.ISSUE_DMG`, underscore): the rule wins (`W.ISSUE-DMG`). |
| 9 | `postingDate.value` | `postedAt` re-printed as `yyyy-MM-dd'T'HH:mm:ss.SSSXXX`, **keeping the source offset**. | "Preserve timezone exactly" = do not convert to UTC. **Sample value contradicts the rule** (no millis, `Z` for a `+02:00` input); the rule wins: `2026-06-01T10:23:00.000+02:00`. Zero offset prints `Z`. |
| 10 | `locationRef` | `warehouse.code`, plus `"-" + warehouse.zone` if zone has a value. | Optional part: dash dropped with the zone. |
| 11-13 | `itemFamily`, `itemVariant`, `itemSize` | SKU split on `-` into **at most three parts**: first / second / **everything after the second `-`**. | **Ambiguity (repeated separator):** `TBL-PINE-XL-LONG` -> family `TBL`, variant `PINE`, size `XL-LONG` (not `XL`). The input schema guarantees at least two dashes. |
| 14 | `quantity.value` | If `type = ISSUE` -> negate; if `RECEIPT` -> as is; **ADJUST and TRANSFER -> as is** (sign already in the source); then round to 3 decimals. | **Ambiguity:** `IF .. ELSIF ..` without `ELSE`. Resolution: implicit else = copy the value unchanged. TRANSFER question (reviewer, unanswered) -> not negated. |
| 15 | `quantity.unit` | `uomlist[unit]`; unknown unit -> source unit unchanged. | Table missing in workbook; reviewer thread answered with a pointer to a sheet that does not exist. Resolution given in section 0. |
| 16 | `lotId` | `lot.id` if it has a value, else omit. | `lot` may itself be `null`. |
| 17 | `lotExpiry.value` | `lot.expiry + "T00:00:00Z"` **only when `lotId` has a value and expiry has a value**. | **Ambiguity:** "Only when lotId present" vs. expiry present alone. Resolution: both are required. The literal `T00:00:00Z` has **no milliseconds** (differs from row 9 on purpose; the rule text wins). `No` = optional. |
| 18 | `reasonText` | For every reason in order: `code`, plus `"|" + text` if text has a value; items joined with `,`. Omit if `reasons` is empty. | **Ambiguity:** reason without text. Resolution: code only, no `|` (`EXP`, not `EXP|`). |
| 19 | `userName` | `movement.user` if it has a value, else omit. | **Contradiction:** Mandatory = `N` but note says "reject if null". Resolution: **the Mandatory flag wins**; null => field omitted, message is *not* rejected. |
| 20 | `docRef` | **Not mapped.** | **Contradiction:** comment says `Do Not Map` while the rule is still filled and the sample shows a value. `Do Not Map` wins; the output schema has no `docRef`. |

## 2. Validations sheet
Intentionally (almost) empty: "no entry specific validations; only source schema validation". Meaning: no extra business rule rejects a message beyond the input schema.

## 3. Version information (deliberately inconsistent)
- File name: `v0.3`.
- Sheet `Version`: last row `0.4` ("Waiting approval", empty status) - dates in four different formats (date cell, `20/05/2026` = 20 May, `20260601` = 1 Jun, `2026-06-15`).
- Column "Updated in version": highest value `0.5` (docRef).
- **Resolution:** the three sources disagree and none is authoritative. The mapping *content* is what is specified; for versioning purposes treat the workbook as "0.5 draft" (content) and record the discrepancy. No rule's behaviour depends on the version.

## 4. Test coverage
- `case1`: ISSUE, offset `+02:00` preserved, lot with expiry, two reasons (second without text), user present, linked doc present (ignored).
- `case2`: RECEIPT with **nulls** (zone, lot id, user), empty reasons, 4-part SKU, unknown unit passed through, `lot.expiry` ignored because `lot.id` is null, negative offset.
- `case3`: ADJUST = **implicit else** branch of the quantity rule, `lot = null`, `Z` offset, lookup hit (`KGM -> KG`), decimal rounding.
