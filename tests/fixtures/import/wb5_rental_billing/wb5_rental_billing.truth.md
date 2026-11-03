# WB5 - Truth file (styles K + L merged): equipment rentals -> billing request

Workbook: `RentalContract_to_BillingRequest_Mapping_v1.xlsx` (sheets `Change Log`, `BillingRequest Mapping`, `Source JSON`, `Target JSON`).
Schemas: `wb5_rental_billing.input.schema.json`, `wb5_rental_billing.output.schema.json`. Tests: `tests/case1..3`.

## 0. Global conventions (resolved)

| Topic | Correct reading |
|---|---|
| Rows | One row per target field; `#` is only a counter. Band rows (ROOT / LINE / CUSTOMER) group the rows. |
| Paths | Source paths are relative to `rental`. Arrays are wrapped as `{ "items": [...] }` (`attributes.items[]`, `lines.items[]`). |
| `[]`, `[*]`, no brackets | In `lines.items[]`, `lines.items[*]` and `lines.items` (no brackets) = every line. `[qualifier=='X']` = filter (every match). |
| Index base | `split(...)[n]` and `lines.items[0]`-style code = **0-based**. The comment "Pipe index [3]" on row 4 is the **1-based ordinal of the same element** as `[2]`. |
| Packed attribute | `attributes.items[qualifier=='BILLING DATA'].value` is a string of `|`-separated fields; field k is `split('|')[k]`. If there are several BILLING DATA attributes, take the **first**. |
| Required | `YES` = mandatory, `NO` = optional. A mandatory field whose source is missing makes the whole message **rejected** (not exercised by the tests: the input schema makes BILLING DATA present in practice). |
| Null / empty / absent | Equivalent; optional target fields without value are omitted; the booleans `hasDeposit`, `isDeposit` are always present. |
| Lookup `uomlist` | Not in the workbook. Correct content: `DAY -> "per day"`, `WEEK -> "per week"`. Unknown or null unit => **omit** `unitLabel`. |
| Dates | Row 4: date part **as written** (first 10 chars, no conversion). Row 7: `yyyyMMdd` **after converting to UTC**. |
| Colours | Grey banding and header fills are decoration. The yellow cell on row 14 = "attention / open"; no functional meaning. |

## 1. Rules

| # | Target | Correct interpretation | Assumptions / deliberate ambiguity -> resolution |
|---|---|---|---|
| 1 | `originCode` | `"RNT001"` if `category` is `LONG` or `LONG-EXT`, else `"RNT002"`. | `IN (...)` is exact match. **Example column contradicts the rule** (`SHORT → RNT003`): the rule wins, `SHORT -> RNT002`. |
| 2 | `billingId` | `contractId`. | - |
| 3 | `currencyCode` | `currency.code`. | - |
| 4 | `ruleDate` | First 10 characters of the third pipe field (`split('|')[2]`), e.g. `2026-04-09`. | **Index ambiguity (deliberate):** expression says `[2]`, comment says "index [3]". Same element: `[2]` is 0-based, `[3]` is 1-based. Time zone is **not** converted. |
| 5 | `bypassRun` | Constant `"N"`. | - |
| 6 | `bypassFlag` | `"Y"` if the packed value has a field at index 4 equal to `Y`; otherwise `"N"` (also when the field is empty or the packed string has fewer fields). | "Not present -> N" covers a short string. Index 4 is 0-based (fifth field). |
| 7 | `createdDate` | `createdAt` converted to UTC, printed `yyyyMMdd`. | **Ambiguity:** "(UTC)" in a format cell. Resolution: convert first, then format (`2026-04-09T23:30:00-05:00` -> `20260410`). Row 4 is intentionally different. |
| 8 | `billingNote` | `value` of the **first** attribute with qualifier `NOTE`; omit if none. | **Ambiguity:** several NOTE attributes (open reviewer question, no reply). Resolution: first match only. |
| 9 | `hasDeposit` | `true` if at least one attribute has qualifier `DEPOSIT`, else `false`. | The value of the attribute is irrelevant. |
| 10 | `lineItems[].seqNo` | `lineNo`. | One output line per input line, same order. |
| 11 | `lineItems[].assetCode` | `equipmentCode` without the prefix `E.` (only if present). | `7-CC-3` (no prefix) stays unchanged. |
| 12 | `lineItems[].chargeNet` | `amount.value` unchanged. | Path without brackets = per line. |
| 13 | `lineItems[].isDeposit` | `kind == "DEP"`. | Enumeration explained in the comment: `RENT`, `DEP`. |
| 14 | `lineItems[].unitLabel` | `uomlist[unit]`, omit if unknown/null. | Table missing, no default; "waiting for confirmation". Resolution: omit (see section 0). |
| 15 | `customer.code` | `split(partyRef,'-')[0]` without prefix `C.`. | - |
| 16 | `customer.type` | `split(partyRef,'-')[1]`. | - |
| 17 | `customer.seq` | `split(partyRef,'-')[2]`. | **Ambiguity (repeated separator):** for `C.NORD-RES-2024-0042` the full split has four parts; index 2 is **`2024`** (the rest `0042` is dropped). The comment's 3-part example hides this. Literal reading of the rule wins. |
| 18-19 | `customer.levyCountry`, `customer.levyRegion` | Mapped only when row 6 yields `"Y"`, and only if the source field has a value. | Condition in prose, no else: otherwise omitted. |

## 2. Change Log
Dates in four formats (date cell, `20260813` = 13 Aug, `21/09/2026` = 21 Sep, `2026-10-02`). Entries "Line 27 HasDeposit" and "Line 25" refer to rows that **do not exist** (the sheet has 19 numbered rows): historical notes, no effect. File name `v1` agrees with the last log entry `1.0`.

## 3. JSON sample sheets
`Source JSON` and `Target JSON` contain `case1`, one line per cell, indentation by non-breaking spaces. The target sample is the exact output of `case1`.

## 4. Test coverage
- `case1`: LONG, four-part customer reference (`seq = "2024"`), two NOTE attributes (first used), deposit present, tax fields mapped, UTC date crossing midnight, unit `MONTH` unknown -> omitted.
- `case2`: SHORT (**else** branch of row 1), packed field index 4 empty -> `bypassFlag = "N"`, no NOTE, no DEPOSIT (`hasDeposit = false`), `state = null`, unit null. Tax fields not mapped.
- `case3`: LONG-EXT, packed string with **fewer fields** (only three) -> `bypassFlag = "N"`, `Z` timestamp, deposit present, date shifts back one day in UTC (`20260430`).
