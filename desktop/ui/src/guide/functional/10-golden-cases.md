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


The **Golden** tab of a mapping lists its cases and which files each has. *Import a case…* takes
the files and copies them in, proposing a name from the input file's. A case can be renamed or
deleted.

The same cases are what the developers' tests and the automatic build run, so what you keep
here is what protects the mapping.

Running the cases from the tool, and seeing which pass, is not there yet: for now they are run with
`mapper test`, and the Run buttons of the view are disabled.
