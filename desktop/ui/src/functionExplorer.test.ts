import { describe, expect, it } from "vitest";
import type { FunctionEntry } from "./api";
import { callOf, filterFunctions } from "./functionExplorer";

const fn = (name: string, doc: string, params: [string, string | null, boolean?][]): FunctionEntry => ({
  name,
  signature: name + "()",
  params: params.map(([n, d, v]) => ({ name: n, annotation: "", default: d, variadic: v ?? false })),
  returns: "",
  doc,
  origin: "built-in",
  builtin: true,
  replaces_builtin: false,
  targets: [],
});

const all = [
  fn("round", "Rounds a number.", [["x", null], ["digits", "0"]]),
  fn("concat", "Joins texts, with a separator.", [["parts", null, true]]),
  fn("split_first", "The part before the separator.", [["s", null], ["sep", null]]),
];

describe("function explorer", () => {
  it("finds by name or description, names that start with the word first", () => {
    expect(filterFunctions(all, "sep").map((f) => f.name)).toEqual(["concat", "split_first"]);
    expect(filterFunctions(all, "ro").map((f) => f.name)).toEqual(["round"]);
    expect(filterFunctions(all, "")).toBe(all);
    expect(filterFunctions(all, "zzz")).toEqual([]);
  });

  it("builds the call from the required arguments, the first one to overwrite", () => {
    expect(callOf(all[0])).toEqual({ call: "round(x)", first: "x" });
    expect(callOf(all[1])).toEqual({ call: "concat(parts)", first: "parts" });
    expect(callOf(all[2])).toEqual({ call: "split_first(s, sep)", first: "s" });
  });
});
