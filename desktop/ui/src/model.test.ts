import { describe, expect, it } from "vitest";
import {
  columnOfMessage,
  diagnosticsByRule,
  expressionOf,
  flatten,
  type FunctionalFile,
  nameOf,
  ruleAt,
  setExpression,
} from "./model";

const field = (id: string, name: string, expression: string) => ({
  kind: "field" as const,
  id,
  description: null,
  field: name,
  type: "str",
  required: true,
  source_path: null,
  transform: { expression, status: "auto" as const, code_override: null, last_auto_version: null },
  validation: { validated: false, needs_review: false, notes: null },
});

const file: FunctionalFile = {
  name: "T",
  id: "t",
  path: null,
  rules: [
    field("a", "A", "$.a"),
    {
      kind: "loop",
      id: "l",
      description: null,
      source: "$.items[*]",
      output: "$.Lines[*]",
      label: "item",
      filter: null,
      rules: [field("b", "B", "@item.b")],
    },
  ],
};

describe("model", () => {
  it("flattens with the loader's rule paths and depths", () => {
    expect(flatten(file.rules).map((r) => [r.path, r.depth])).toEqual([
      ["rules[0]", 0],
      ["rules[1]", 0],
      ["rules[1].rules[0]", 1],
    ]);
  });

  it("finds a rule by path", () => {
    const rule = ruleAt(file, "rules[1].rules[0]");
    expect(rule && nameOf(rule)).toBe("B");
    expect(ruleAt(file, "rules[5]")).toBeUndefined();
  });

  it("edits the expression column per kind", () => {
    const copy = structuredClone(file);
    const loop = ruleAt(copy, "rules[1]")!;
    setExpression(loop, "@.x > 1");
    expect(expressionOf(loop)).toBe("@.x > 1");
    setExpression(loop, "");
    expect(expressionOf(loop)).toBe("");
  });

  it("groups diagnostics by rule for one file", () => {
    const d = (rule: string | null, file: string | null) => ({
      severity: "error" as const,
      file,
      rule,
      message: "m",
    });
    const grouped = diagnosticsByRule(
      [
        d("rules[0]", "mappings/functional/t.fn.yaml"),
        d(null, "mappings/functional/t.fn.yaml"),
        d("rules[0]", "mappings/functional/other.fn.yaml"),
        d(null, null),
      ],
      "mappings/functional/t.fn.yaml",
    );
    expect(grouped.get("rules[0]")).toHaveLength(1);
    expect(grouped.get("")).toHaveLength(2);
  });

  it("names the column a message is about", () => {
    expect(columnOfMessage("'type' must be one of str, int — got 'x'")).toBe("type");
    expect(columnOfMessage("transform.status is 'manual' but code_override is empty")).toBe(
      "expression",
    );
    expect(columnOfMessage("something else entirely")).toBeNull();
  });
});
