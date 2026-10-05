import { describe, expect, it } from "vitest";
import type { GoldenResult } from "./api";
import {
  diffLines,
  goldenDiagnostics,
  maybeFalsePositive,
  tally,
  unavailableFunctions,
  verdict,
  whyFailed,
} from "./goldenResult";

const result = (over: Partial<GoldenResult>): GoldenResult => ({
  name: "c",
  passed: true,
  output: {},
  errors: [],
  expected_errors: null,
  diff: "",
  message: "",
  target: "plsql",
  inconclusive: false,
  values: {},
  expected_values: null,
  ...over,
});

describe("golden results", () => {
  it("tells pass, fail and shown-only, and counts them", () => {
    const all = [result({}), result({ passed: false }), result({ passed: null }), result({})];
    expect(all.map(verdict)).toEqual(["pass", "fail", "shown", "pass"]);
    expect(tally(all)).toEqual({ pass: 2, fail: 1, shown: 1, inconclusive: 0 });
  });

  it("says why a case failed", () => {
    expect(whyFailed(result({ passed: false, diff: "-a\n+b" }))).toEqual(["the output is not the expected one"]);
    expect(
      whyFailed(result({ passed: false, errors: [{ rule: "lines", cause: "x", path: null, regex: false, expected: false, unavailable: [] }], expected_errors: null })),
    ).toEqual(["rules reported errors (lines) and none were expected"]);
    expect(
      whyFailed(result({ passed: false, errors: [{ rule: "a", cause: "x", path: null, regex: false, expected: false, unavailable: [] }], expected_errors: ["b"] })),
    ).toEqual(["rule errors were [a], expected [b]"]);
    expect(whyFailed(result({ passed: false, message: "no compiled mapping" }))).toEqual(["no compiled mapping"]);
  });

  it("marks the lines of a diff", () => {
    const lines = diffLines("--- expected\n+++ actual\n@@ -1 +1 @@\n-a\n+b\n c\n");
    expect(lines.map((l) => l.kind)).toEqual(["ctx", "ctx", "ctx", "del", "add", "ctx"]);
  });
});

describe("golden marks on the grid", () => {
  const error = (over: object) => ({
    rule: "r",
    cause: "boom",
    path: "rules[1]",
    regex: false,
    expected: false,
    unavailable: [] as string[],
    ...over,
  });

  it("marks the rows of the rules that failed unexpectedly, and only those", () => {
    const marks = goldenDiagnostics(
      [
        result({ name: "a", errors: [error({}), error({ rule: "q", path: "rules[2]", expected: true })] }),
        result({ name: "b", errors: [error({ rule: "m", path: null })] }), // a .map.py: no row
      ],
      "mappings/functional/orders.fn.yaml",
    );
    expect(marks).toHaveLength(1);
    expect(marks[0]).toMatchObject({ severity: "error", rule: "rules[1]", file: "mappings/functional/orders.fn.yaml" });
    expect(marks[0].message).toContain("Golden case a: boom");
  });

  it("calls a failure of a rule with a regular expression a possible false positive, off Python", () => {
    expect(maybeFalsePositive(error({ regex: true }), "plsql")).toBe(true);
    expect(maybeFalsePositive(error({ regex: true }), "python")).toBe(false);
    expect(maybeFalsePositive(error({}), "plsql")).toBe(false);
    const [mark] = goldenDiagnostics([result({ errors: [error({ regex: true })] })], "f");
    expect(mark.severity).toBe("warning");
    expect(mark.message).toContain("false positive");
    const [real] = goldenDiagnostics([result({ target: "python", errors: [error({ regex: true })] })], "f");
    expect(real.severity).toBe("error");
  });
});

describe("rules that could not run on Python", () => {
  const skipped = result({
    passed: false,
    inconclusive: true,
    errors: [
      { rule: "wh", cause: "MissingImplementation: f", path: "rules[1]", regex: false, expected: false, unavailable: ["f", "g"] },
    ],
  });

  it("makes the verdict inconclusive, not a failure, and says which functions", () => {
    expect(verdict(skipped)).toBe("inconclusive");
    expect(tally([skipped, result({})])).toEqual({ pass: 1, fail: 0, shown: 0, inconclusive: 1 });
    expect(unavailableFunctions(skipped)).toEqual(["f", "g"]);
    expect(whyFailed(skipped)[0]).toBe("some rules did not run: no Python code for f, g");
  });

  it("marks the row amber, with the functions, even when the case expected the rule to fail", () => {
    const [mark] = goldenDiagnostics(
      [{ ...skipped, errors: [{ ...skipped.errors[0], expected: true }] }],
      "f",
    );
    expect(mark.severity).toBe("warning");
    expect(mark.message).toContain("no code for Python (f, g)");
  });
});
