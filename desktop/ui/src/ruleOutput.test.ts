import { describe, expect, it } from "vitest";
import type { GoldenResult } from "./api";
import { baseName, outputCell, outputLight } from "./ruleOutput";

const run = (values: Record<string, unknown>, expected: Record<string, unknown> | null): GoldenResult => ({
  name: "c",
  passed: null,
  output: {},
  errors: [],
  expected_errors: null,
  diff: "",
  message: "",
  target: "plsql",
  inconclusive: false,
  values,
  expected_values: expected,
});

describe("the Output column", () => {
  it("shows the value alone for an input without expectation", () => {
    const r = run({ "rules[0]": "A1", "rules[1]": [1, 2] }, null);
    expect(outputCell(r, "rules[0]")).toEqual({ text: "A1", state: "", tooltip: "A1" });
    expect(outputCell(r, "rules[1]")?.text).toBe("[1,2]");
    expect(outputCell(r, "rules[2]")).toBeNull();
    expect(outputCell(null, "rules[0]")).toBeNull();
  });

  it("marks what differs from the expected output and says what was expected", () => {
    const r = run({ "rules[0]": "A1", "rules[1]": 5 }, { "rules[0]": "A1", "rules[1]": 6, "rules[2]": "x" });
    expect(outputCell(r, "rules[0]")?.state).toBe("same");
    const diff = outputCell(r, "rules[1]");
    expect(diff?.state).toBe("diff");
    expect(diff?.tooltip).toBe("Gave: 5\nExpected: 6");
    expect(outputCell(r, "rules[2]")).toMatchObject({ text: "(nothing)", state: "diff" });
  });

  it("compares objects and lists by content", () => {
    const r = run({ "rules[0]": { a: 1, b: [1, 2] } }, { "rules[0]": { b: [1, 2], a: 1 } });
    expect(outputCell(r, "rules[0]")?.state).toBe("same");
  });

  it("lights green for a case or a file that is there", () => {
    expect(outputLight(null, ["a"], false)).toBe("unknown");
    expect(outputLight({ kind: "case", name: "a" }, ["a"], false)).toBe("ok");
    expect(outputLight({ kind: "case", name: "gone" }, ["a"], false)).toBe("missing");
    expect(outputLight({ kind: "file", path: "/x.json" }, [], false)).toBe("ok");
    expect(outputLight({ kind: "file", path: "/x.json" }, [], true)).toBe("missing");
    expect(baseName("/a/b.json")).toBe("b.json");
    expect(baseName("C:\\x\\y.json")).toBe("y.json");
  });
});
