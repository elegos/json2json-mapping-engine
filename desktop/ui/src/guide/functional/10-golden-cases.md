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

The same cases are what the developers' tests and the automatic build run, so what you keep here
is what protects the mapping.

Running the cases from the tool, and seeing which pass, is not there yet: for now they are run with
`mapper test`, and the Run buttons of the view are disabled.
