import { describe, expect, it } from "vitest";
import { type ConfigOption, issuesAt, setAt, shownValue, tableAt } from "./projectConfig";
import {
  columnOfMessage,
  addEntry,
  filterRows,
  changedColumns,
  savedIndex,
  insertionPoint,
  lookups,
  parseTyped,
  parseValue,
  renameEntry,
  sourceOf,
  showValue,
  type Row,
  type Rule,
  pushRecent,
  rowIssues,
  treePrefix,
  visibleRows,
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
  source_constant: null,
  has_constant: false,
  transform: { expression, status: "auto" as const, code_override: null, last_auto_version: null },
  validation: { validated: false, needs_review: false, notes: null },
});

const file: FunctionalFile = {
  name: "T",
  id: "t",
  path: null,
  paths: { root: null, aliases: {} },
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
    expect(nameOf(file.rules[0])).toBe("A");
    expect(nameOf(file.rules[1])).toBe("Lines[*]");
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

  it("draws the tree and folds a loop", () => {
    const rows = flatten(file.rules);
    expect(rows.map(treePrefix)).toEqual(["", "", "└─ "]);
    expect(visibleRows(rows, new Set(["rules[1]"])).map((r) => r.path)).toEqual([
      "rules[0]",
      "rules[1]",
    ]);
  });

  it("lists what is wrong with a row", () => {
    const rule = ruleAt(file, "rules[0]")!;
    expect(rowIssues(rule, [])).toEqual(["Not validated"]);
    const d = { severity: "error" as const, file: null, rule: null, message: "'type' is bad" };
    expect(rowIssues(rule, [d])[0]).toBe("Invalid Type: 'type' is bad");
  });

  it("keeps the ten most recent projects, latest first", () => {
    let recent: string[] = [];
    for (let i = 0; i < 12; i++) recent = pushRecent(recent, `/p${i}`);
    recent = pushRecent(recent, "/p5");
    expect(recent).toHaveLength(10);
    expect(recent[0]).toBe("/p5");
    expect(recent.filter((d) => d === "/p5")).toHaveLength(1);
  });
});

describe("insertionPoint", () => {
  const leaf = (path: string): Row => ({
    path,
    depth: 0,
    rule: { kind: "field", id: null, description: null, field: "A", type: "str", required: true, source_path: null, source_constant: null, has_constant: false, transform: { expression: null, status: "auto", code_override: null, last_auto_version: null }, validation: { validated: false, needs_review: false, notes: null } },
    guides: [],
    last: false,
    hasChildren: false,
  });
  it("appends to the root when nothing is selected", () => {
    expect(insertionPoint(undefined)).toEqual({ parent: null, index: null });
  });
  it("goes after a selected root field", () => {
    expect(insertionPoint(leaf("rules[2]"))).toEqual({ parent: null, index: 3 });
  });
  it("goes after a selected nested field, in its container", () => {
    expect(insertionPoint(leaf("rules[3].rules[0]"))).toEqual({ parent: "rules[3]", index: 1 });
  });
  it("goes inside a selected container", () => {
    const row = { ...leaf("rules[3]"), rule: { kind: "object", id: null, description: null, output: "$.X", guard: null, source: null, rules: [] } as Rule };
    expect(insertionPoint(row)).toEqual({ parent: "rules[3]", index: null });
  });
});

describe("lookup entries", () => {
  it("parses typed text back to a value", () => {
    expect(parseValue("12")).toBe(12);
    expect(parseValue("true")).toBe(true);
    expect(parseValue("null")).toBeNull();
    expect(parseValue("EUR")).toBe("EUR");
    expect(parseValue('"12"')).toBe("12");
    expect(parseValue('"broken')).toBe('"broken');
  });
  it("parses by the declared type and leaves what does not fit as text", () => {
    expect(parseTyped("12", "str")).toBe("12");
    expect(parseTyped("12", "int")).toBe(12);
    expect(parseTyped("1.5", "int")).toBe("1.5");
    expect(parseTyped("1.5", "number")).toBe(1.5);
    expect(parseTyped("true", "bool")).toBe(true);
    expect(parseTyped("yes", "bool")).toBe("yes");
    expect(parseTyped("12", null)).toBe(12);
  });
  it("shows strings bare and the rest as JSON", () => {
    expect(showValue("EUR")).toBe("EUR");
    expect(showValue(12)).toBe("12");
    expect(showValue(null)).toBe("null");
  });
  it("renames a key in place and refuses a taken or empty one", () => {
    const entries = { a: 1, b: 2, c: 3 };
    expect(Object.keys(renameEntry(entries, "b", "x"))).toEqual(["a", "x", "c"]);
    expect(renameEntry(entries, "b", "c")).toBe(entries);
    expect(renameEntry(entries, "b", "")).toBe(entries);
  });
  it("adds an entry with a free key", () => {
    expect(Object.keys(addEntry(addEntry({})))).toEqual(["key", "key2"]);
  });
  it("finds lookups at any depth with their path", () => {
    const lookup = { kind: "lookup", id: null, description: null, label: "L", entries: { a: 1 }, type: null } as const;
    const found = lookups([
      lookup,
      { kind: "object", id: null, description: null, output: "$.X", guard: null, source: null, rules: [lookup] },
    ]);
    expect(found.map((f) => f.path)).toEqual(["rules[0]", "rules[1].rules[0]"]);
  });
});

describe("project config helpers", () => {
  const values = { project: { target: "plsql" }, target: { plsql: { schema: "S" } } };
  it("reads a table, missing ones as empty", () => {
    expect(tableAt(values, ["target", "plsql"])).toEqual({ schema: "S" });
    expect(tableAt(values, ["nope", "x"])).toEqual({});
  });
  it("sets and removes a key without touching the original", () => {
    const changed = setAt(values, ["target", "plsql"], "error_code", -20000);
    expect(tableAt(changed, ["target", "plsql"])).toEqual({ schema: "S", error_code: -20000 });
    expect(tableAt(values, ["target", "plsql"])).toEqual({ schema: "S" });
    expect(tableAt(setAt(changed, ["target", "plsql"], "schema", undefined), ["target", "plsql"])).toEqual({
      error_code: -20000,
    });
  });
  it("creates the tables on the way", () => {
    expect(setAt({}, ["compiler", "default_choices"], "format", "truncate")).toEqual({
      compiler: { default_choices: { format: "truncate" } },
    });
  });
  it("shows the default for an absent key and picks the issues of one path", () => {
    const option: ConfigOption = { key: "k", kind: "bool", help: "", required: false, default: true, choices: [] };
    expect(shownValue({}, option)).toBe(true);
    expect(shownValue({ k: false }, option)).toBe(false);
    expect(issuesAt([{ path: "a.b", message: "m" }, { path: "a.c", message: "n" }], ["a"], "b")).toEqual(["m"]);
  });
});

describe("sourceOf", () => {
  const field = (extra: object) =>
    ({
      kind: "field", id: null, description: null, field: "A", type: "int", required: true,
      source_path: null, source_constant: null, has_constant: false,
      transform: { expression: null, status: "auto", code_override: null, last_auto_version: null },
      validation: { validated: false, needs_review: false, notes: null },
      ...extra,
    }) as Rule;
  it("shows a path as written and a constant as JSON", () => {
    expect(sourceOf(field({ source_path: "$.id" }))).toBe("$.id");
    expect(sourceOf(field({ has_constant: true, source_constant: 27 }))).toBe("27");
    expect(sourceOf(field({ has_constant: true, source_constant: "x" }))).toBe('"x"');
    expect(sourceOf(field({ has_constant: true, source_constant: null }))).toBe("null");
  });
});

describe("unsaved changes", () => {
  it("lists the columns that differ from the saved rule", () => {
    const before = ruleAt(file, "rules[0]")!;
    const after = structuredClone(before);
    expect(changedColumns(after, before).size).toBe(0);
    if (after.kind === "field") {
      after.transform.expression = "$.b";
      after.validation.notes = "n";
    }
    expect([...changedColumns(after, before)].sort()).toEqual(["expression", "notes"]);
  });
  it("marks a rule with no saved counterpart as new", () => {
    expect([...changedColumns(file.rules[0], undefined)]).toEqual(["*"]);
  });
  it("finds saved rules by id, then by path", () => {
    const index = savedIndex(file.rules);
    expect(index.byId.get("b")).toBe(file.rules[1].kind === "loop" ? file.rules[1].rules[0] : undefined);
    expect(index.byPath.get("rules[0]")).toBe(file.rules[0]);
  });
});

describe("an object that selects an element", () => {
  it("shows its condition in the Source column", () => {
    const rule = {
      kind: "object", id: null, description: null, output: "$.X", guard: null,
      source: "$.list[@.d == 'x']", rules: [],
    } as Rule;
    expect(sourceOf(rule)).toBe("$.list[@.d == 'x']");
    expect(sourceOf({ ...rule, source: null } as Rule)).toBe("");
  });
});

describe("filterRows", () => {
  const rows = flatten(file.rules);
  it("shows everything without a filter", () => {
    expect(filterRows(rows, "  ")).toBe(rows);
  });
  it("matches the rule id or the Target, ignoring case", () => {
    expect(filterRows(rows, "A").map((r) => r.path)).toEqual(["rules[0]"]);
    expect(filterRows(rows, "b").map((r) => r.path)).toEqual(["rules[1]", "rules[1].rules[0]"]);
  });
  it("keeps the containers a match is in, and the rules of a matching container", () => {
    expect(filterRows(rows, "lines").map((r) => r.path)).toEqual(["rules[1]", "rules[1].rules[0]"]);
    expect(filterRows(rows, "zzz")).toEqual([]);
  });
});

describe("filterRows with a dotted path", () => {
  const tree: Rule[] = [
    field("n", "Note", "$.n"),
    {
      kind: "object", id: "ch", description: null, output: "$.Channel", guard: null, source: null,
      rules: [
        {
          kind: "object", id: "cu", description: null, output: "@.Customer", guard: null, source: null,
          rules: [field("na", "Name", "@.n"), field("co", "Code", "@.c")],
        },
        field("nm", "Name", "@.m"),
      ],
    },
    {
      kind: "loop", id: "ln", description: null, source: "$.items[*]", output: "$.Lines[*]", label: null, filter: null,
      rules: [field("sk", "Sku", "@.s"), field("nn", "Name", "@.n2")],
    },
  ];
  const rows = flatten(tree);
  const found = (text: string) => filterRows(rows, text).map((r) => nameOf(r.rule));

  it("matches the last part against the rule and the earlier ones against its containers", () => {
    expect(found("customer.name")).toEqual(["Channel", "Customer", "Name"]);
    expect(found("channel.customer.name")).toEqual(["Channel", "Customer", "Name"]);
    expect(found("lines.name")).toEqual(["Lines[*]", "Name"]);
  });
  it("lets the parts skip containers", () => {
    expect(found("channel.name")).toEqual(["Channel", "Customer", "Name", "Name"]);
  });
  it("shows everything inside a container when the last part is empty", () => {
    expect(found("customer.")).toEqual(["Channel", "Customer", "Name", "Code"]);
  });
  it("still shows the rules of a container that matches alone", () => {
    expect(found("lines")).toEqual(["Lines[*]", "Sku", "Name"]);
    expect(found("channel.zzz")).toEqual([]);
  });
});
