# Golden cases

A **golden case** is an example you are sure about: an input, and the output it must give. After
every change, the cases tell you whether the mapping still does what it should.

A case is made of up to three files, in `tests/golden/<mapping>/`:

| File | What it holds |
|---|---|
| `<case>.input.json` | The input document. |
| `<case>.expected.json` | The output expected for it. |
| `<case>.expected_errors.json` | The rules expected to report an error, if any. |

## In the tool

```figure
{"src": "golden.png", "alt": "The Golden view"}
```

The **Golden** tab of a mapping lists its cases and which files each has.

- **Import a case…** takes files you already have and copies them in, proposing a name from the
  input file's.
- **New case…** creates a case with an empty input, `{}`, to fill in.
- The name of a case opens it in the editor; the pencil renames it and the cross deletes it.

## The editor

```figure
{"src": "golden-editor.png", "alt": "A golden case in the editor"}
```

Each file is edited as JSON, with a note under it saying whether it is valid. **Format** indents
it. The expected output and the expected errors are optional: add one when you need it, and
**Remove this file** takes it away again. The expected errors are a list of rule ids, such as
`["rules[0]"]`: the rules that must report an error for this input.

**Save** writes the files you changed, and refuses a file that is not valid. Leaving the case with
changes not saved asks first.

## Running the cases

```figure
{"src": "golden-run.png", "alt": "The results of running the golden cases"}
```

**Execute all** runs every case, and the ▶ of a row runs that one. The cases run on the saved
mapping, with no database: if the mapping has changes you have not saved, the tool offers to save
them first. Each case gets a result:

| Result | Meaning |
|---|---|
| **PASS** | The output is the expected one, and the rules that reported an error are the ones expected. |
| **FAIL** | The output differs, or other rules failed (or did not fail) than expected. |
| **output only** | The case has no expected output: you see what the mapping gives, nothing is judged. |

Click a result to see why: which rules reported an error and the cause, and the output, or its
difference from the expected one (green lines are what the mapping gave, red what was expected).

**Record as expected…** makes the output of a case, and the rules that failed, its expected
result. Look at the output first: recording what is wrong makes the case pass for the wrong
reason. It replaces the expected files of that case.

The same cases are what the developers' tests and the automatic build run, on every backend, so
what you keep here is what protects the mapping.
