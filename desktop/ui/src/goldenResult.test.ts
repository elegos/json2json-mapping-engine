import { describe, expect, it } from "vitest";
import type { GoldenResult } from "./api";
import { diffLines, tally, verdict, whyFailed } from "./goldenResult";

const result = (over: Partial<GoldenResult>): GoldenResult => ({
  name: "c",
  passed: true,
  output: {},
  errors: [],
  expected_errors: null,
  diff: "",
  message: "",
  ...over,
});

describe("golden results", () => {
  it("tells pass, fail and shown-only, and counts them", () => {
    const all = [result({}), result({ passed: false }), result({ passed: null }), result({})];
    expect(all.map(verdict)).toEqual(["pass", "fail", "shown", "pass"]);
    expect(tally(all)).toEqual({ pass: 2, fail: 1, shown: 1 });
  });

  it("says why a case failed", () => {
    expect(whyFailed(result({ passed: false, diff: "-a\n+b" }))).toEqual(["the output is not the expected one"]);
    expect(
      whyFailed(result({ passed: false, errors: [{ rule: "lines", cause: "x" }], expected_errors: null })),
    ).toEqual(["rules reported errors (lines) and none were expected"]);
    expect(
      whyFailed(result({ passed: false, errors: [{ rule: "a", cause: "x" }], expected_errors: ["b"] })),
    ).toEqual(["rule errors were [a], expected [b]"]);
    expect(whyFailed(result({ passed: false, message: "no compiled mapping" }))).toEqual(["no compiled mapping"]);
  });

  it("marks the lines of a diff", () => {
    const lines = diffLines("--- expected\n+++ actual\n@@ -1 +1 @@\n-a\n+b\n c\n");
    expect(lines.map((l) => l.kind)).toEqual(["ctx", "ctx", "ctx", "del", "add", "ctx"]);
  });
});
