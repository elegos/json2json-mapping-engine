# WB7 - Truth file: formal requirements, Word, schemas inside the document

`QuoteToOrder_spec_rev2.2.docx` - header says **Revision 2.3**, the change history ends at **2.3**, the file name says `rev2.2`:
the name is stale (version conflict to ask about; resolution 2.3). Requirements are a table `ID | Target | Requirement | Status`;
conventions are declared once in section 2 (1-based indices, UTC, rounding, omit-if-missing).

| Req | Correct reading | Notes / deliberate difficulty |
|---|---|---|
| 01 | `"ORD-" + number` | - |
| 02 | `issuedAt` -> UTC -> `yyyy-MM-dd` | Offset conversion can change the day (case1: `23:30-02:00` is the next day in UTC). |
| 03, 06 | copy | - |
| 04 | trim | "without leading and trailing blanks" = trim. |
| 05 | `vatId`, omitted when absent/null | - |
| 07 | loop over `lines`; `pos` = running number **starting at 1** | the 1-base is declared in section 2, not in the row. |
| 08 | `unitPrice * (1 - discountPct/100)`, rounded half up to 2 decimals | "when there is one": discount absent/null = no discount. Rounding happens **here** (case1: `10.005 * 0.9 = 9.0045 -> 9.00`). |
| 09 | `qty * netPrice(REQ-08, already rounded)`, rounded to 2 | refers to another requirement (cross-reference): uses the rounded net price. |
| 10 | sum of `lineTotal`, 2 decimals | sum of the rounded totals, not recomputed. |
| 11 | `orderDate(REQ-02)` + `paymentDays` days; 30 when absent | uses the UTC date of REQ-02, not the local one. |
| 12 | `incoterm`, default `"EXW"` | highlighted (changed in 2.2). |
| 13 | constant `"NEW"` | - |
| 14 | `lines[1].sku` = first line | highlighted (new in 2.3); 1-based by section 2. |
| 15 | **removed**: do not generate `channel` | struck-through row, status "Removed in 2.3". Not in the output schema either. |
| 16 | validation: reject the whole message if `vatId` is present and not exactly 11 digits | not a field rule; test `case3` expects `{"__rejected__": "REQ-16"}` (convention of this fixture for "no order produced"). |

Expected discrepancies: version conflict (file name 2.2 vs header 2.3); `channel` (REQ-15) is removed in the document and absent from the
schemas - consistent, so no schema error. Schemas in the appendix equal the files provided (`origin: found_in_document`).
Tests: case1 (offset day change, discounts, rounding, custom terms), case2 (no discount, no VAT, defaults), case3 (rejected).
