import { describe, expect, it } from "vitest";
import { changedRoles, firstProblem, formatJson, type Files, jsonProblem } from "./goldenEdit";

describe("golden case files", () => {
  it("accepts JSON, and for the errors only a list of texts", () => {
    expect(jsonProblem("input", '{"a": [1, 2]}')).toBeNull();
    expect(jsonProblem("input", "{")).toMatch(/^Not valid JSON/);
    expect(jsonProblem("errors", '["rules[0]"]')).toBeNull();
    expect(jsonProblem("errors", "[]")).toBeNull();
    expect(jsonProblem("errors", "[1]")).toMatch(/list of rule ids/);
    expect(jsonProblem("errors", '{"a": 1}')).toMatch(/list of rule ids/);
    expect(jsonProblem("rejected", '["REQ-16"]')).toBeNull();
    expect(jsonProblem("warnings", "[1]")).toMatch(/list of check codes/);
  });

  it("indents, and refuses what is not JSON", () => {
    expect(formatJson('{"a":[1,2]}')).toBe('{\n  "a": [\n    1,\n    2\n  ]\n}');
    expect(() => formatJson("{")).toThrow();
  });

  it("tells what changed and the first thing in the way of saving it", () => {
    const saved: Files = { input: "{}\n", expected: null, errors: "[]\n", rejected: null, warnings: null };
    expect(changedRoles(saved, saved)).toEqual([]);
    expect(changedRoles(saved, { ...saved, expected: "{}" })).toEqual(["expected"]);
    expect(firstProblem(saved, { ...saved, expected: "{", errors: null })).toEqual({
      role: "expected",
      message: expect.stringMatching(/Not valid JSON/),
    });
    expect(firstProblem(saved, { ...saved, errors: null })).toBeNull(); // removing a file is fine
    expect(firstProblem(saved, { ...saved, input: null })?.role).toBe("input");
  });
});
