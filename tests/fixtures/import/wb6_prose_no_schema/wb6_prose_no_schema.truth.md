# WB6 - Truth file: pure prose, Word, NO schema

Document: `Spec_DeliveryNotice_draft.docx`. There is no JSON Schema in the document: the files under `_hidden/` are the schemas the
author had in mind. **They must never be given to the reader**; they exist to (a) evaluate the schema the reader infers and (b) run
`_hidden/tests/` against the project it generates. Every rule is a *guess with a confirmation question*; the expected outcome is a
plan with `schemas.*.origin = "inferred"`, confidence `guess`/`low` on most rules, and the questions below.

Expected reader behaviour: version `1.0` assumed (no version declared); one mapping; no layout table (`rule_unit = paragraph`);
functional labels are not technical names, so target/source names are *proposed* (see the hidden schemas for the intended ones).

| # | Text (paragraph) | Intended reading | Why it is hard / expected question |
|---|---|---|---|
| 1 | "identifier: identifier of the order derived from the shipment's list of orders" | One notice per order; `id = order.ref`. | Does it say the first order, one per order, or a derived key? Section 1 settles "one for each order": the loop is over `shipment.orders`. Question: which field of the order is the identifier (`ref`)? |
| 2 | Recipient | `customer.name` upper-cased. | Which "name": the customer's, per the text. |
| 3 | Phone | `customer.phone` with spaces removed; omitted if missing **or empty**. | Section 4 contradicts ("as it arrives, without changes"); the specific rule (section 2) prevails. Question to ask. |
| 4 | Address | `street + ", " + zip + ", " + city` (each separated by a comma). | "separated by commas": between all three, or `zip city` together? Resolution: all three, in the order named. |
| 5 | Total weight | Sum of `weightKg` over the orders **kept** (see 10), x1000, integer grams; same value on every notice. | Per order or per shipment? The text says "of the shipment's orders". Does it include ignored orders? Resolution: only kept ones (an ignored order has no weight anyway). |
| 6 | Urgent | `priority == "H"`. | "high priority" is not a code: the value `H` is only known from the hidden schema; question: which value means high? |
| 7 | Delivery date | `plannedDate` as `dd/MM/yyyy`. | - |
| 8 | Carrier code | `carrier.code[:3].upper()`. | Shorter codes are kept whole. |
| 9 | Notes | `notes` if present; if `weightKg > 30` append `"Handling by two operators"`; join the two with `"; "`. | Separator not stated; "more than 30" = strictly greater (30 exactly does not add it). Question: separator. |
| 10 | Section 3 | Orders with no weight (null/missing) produce no notice. | A **global rule in a different section** from the fields it affects. Zero weight is a weight (section 4 last line). |
| 11 | Section 3 | A field without value is omitted; never `null` or `""`. | Global null rule. |

Expected discrepancies: none can be computed against a schema (none given); `no_schema` flag on every rule.
`_hidden/tests/case1..3`: case1 mixes everything (kept + ignored order, spaces in phone, 30 kg exactly, > 30 kg, notes + heavy);
case2 is a single simple order (month/day swap check: `2026-12-01` -> `01/12/2026`); case3 has no order with weight -> `{"notices": []}`.
