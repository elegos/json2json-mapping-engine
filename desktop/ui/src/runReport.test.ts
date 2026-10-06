import { describe, expect, it } from "vitest";
import type { GoldenResult } from "./api";
import { dirName, inputDialogDir, mappedFilePath } from "./ruleOutput";
import { runReport } from "./runReport";

const result = (errors: GoldenResult["errors"]): GoldenResult => ({
  name: "x",
  passed: null,
  output: {},
  errors,
  expected_errors: null,
  diff: "",
  message: "",
  target: "python",
  inconclusive: false,
  values: {},
  expected_values: null,
});
const error = (rule: string, cause: string, unavailable: string[] = []) => ({
  rule,
  cause,
  path: null,
  regex: false,
  expected: false,
  unavailable,
});

describe("runReport", () => {
  it("says there are no errors", () => {
    expect(runReport(result([]))).toEqual({ ok: true, label: "No errors", lines: [], paths: [] });
  });
  it("gives the row of each rule that failed", () => {
    const r = runReport(result([{ ...error("a", "boom"), path: "rules[0].rules[1]" }, error("b", "bad")]));
    expect(r.paths).toEqual(["rules[0].rules[1]", null]);
  });
  it("lists the rules that failed with their cause", () => {
    const r = runReport(result([error("a", "boom"), error("b", "bad", ["f"])]));
    expect(r.ok).toBe(false);
    expect(r.label).toBe("2 errors");
    expect(r.lines).toEqual(["a: boom", "b: did not run, no Python code for f"]);
    expect(runReport(result([error("a", "boom")])).label).toBe("1 error");
  });
});

describe("dialog folders and file names", () => {
  it("starts in the input's folder, else the last one, else the project", () => {
    expect(inputDialogDir("/in/a.json", "/last", "/proj")).toBe("/in");
    expect(inputDialogDir(null, "/last", "/proj")).toBe("/last");
    expect(inputDialogDir(null, null, "/proj")).toBe("/proj");
    expect(inputDialogDir(null, null, null)).toBeUndefined();
    expect(dirName("a.json")).toBe("");
    expect(dirName("C:\\in\\a.json")).toBe("C:\\in");
  });
  it("proposes the input's name with .mapped before .json", () => {
    expect(mappedFilePath({ kind: "file", path: "/in/order-1.json" }, "/proj")).toBe("/in/order-1.mapped.json");
    expect(mappedFilePath({ kind: "case", name: "two_lines" }, "/proj")).toBe("/proj/two_lines.mapped.json");
  });
});
