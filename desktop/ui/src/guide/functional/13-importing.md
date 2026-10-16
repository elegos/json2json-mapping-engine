# Importing a document

When the rules are already written in a **functional document** (a spreadsheet, a Word file, a PDF
or a text), the tool can read it and propose the rules for you. An assistant (Claude Code or Codex,
installed on this computer) does the reading. **Nothing is written into the project until you apply
the import**: you answer what the assistant could not decide, review what it proposes, and only then
the mapping is created.

Start from the wizard button (🧙‍♂️ in the toolbar): **Import a document…**.

| Step | What it is for |
|---|---|
| **Document** | Choose the document and the assistant. |
| **Run** | The assistant reads the document; you see what it does and answer its questions as they come. |
| **Questions** | The questions still open, if any. |
| **Review** | The proposed rules, with the words of the document each one comes from. |
| **Apply** | Writes the mapping. |

## Document

```figure
{"src": "import-document.png", "alt": "The Document step of an import"}
```

Pick the document and the assistant. The profile (how this kind of document is read), the name of
the mapping and the input and output JSON Schemas are optional: left empty, the assistant proposes
them and asks about what it cannot tell. The text of the document is sent to the assistant you
choose and nowhere else; the assistant may write only inside the project's `import/` folder.

## Run

```figure
{"src": "import-run.png", "alt": "A run in progress, with a question to answer"}
```

A short document is read in one run. A **long** one is read in **batches**, several at a time: the
assistant first surveys the whole document and sorts every row of it, then translates the batches.
While it works:

- The **progress** line says how many batches are done and how many are running.
- **The engine is expected to lack…** is a forecast, not an error: what the assistant expects the
  engine not to be able to express, counted before a rule is written, with the rows that wait for
  it. Some turn out to be written after all; the review shows what really happened.
- A **question** it cannot answer from the document appears on the right. The run does not wait for
  you: until you answer, the rules that depend on it use the proposal and are marked as **guesses**.
  An answer you give now is read by the batches that come next, and the rules it touches are read
  again at the end.
- If the assistant is refused a permission, the run says what it asked for; **Allow and run again**
  allows it and runs again.

The imports of a project are listed on the Document step. One that is not fully translated yet
shows **Translate the rest**, which continues with the batches that are left; **Continue**, **Redo
all**, **New version…** and **Delete…** are beside it.

## Questions and review

The **Questions** step lists what is still open. Each answer is used for every rule it touches; a
question you skip is read the way the assistant proposes.

```figure
{"src": "import-review.png", "alt": "The Review step of an import"}
```

The **Review** shows the rules by confidence (high, medium, low, guess), with the ones that need a
look first. For the selected rule it shows **the words of the document** it comes from and where they
are, what the assistant understood, and the rule it proposes. **Accept** or **Reject** it, or, if it
is not right, write what it got wrong in the note and **Ask again with this note**: the assistant
reads that rule again. The other tabs hold the validations, lookups and golden cases it proposes,
the **discrepancies** it found between the document and the schemas, and the **coverage**: which rows
of the document became rules and which did not, and why.

## Apply

**Apply…** writes the mapping to `mappings/functional/`. The window says how many rules are written,
how many are not reviewed (they are flagged for review when they are not high-confidence), whether
the working copy passes the checks, and what is missing: questions still open, rules with no proposal
(a missing function or an unanswered question) and required output fields with no rule. Writing
the mapping with required fields missing needs an explicit tick.

The rules come out as any others: you can edit them in the grid, and **Validated** and **To review**
work as usual. The import stays in the list: you can view it again, **Redo all** or start a **New
version** of it when the document changes.
