import { describe, expect, it } from "vitest";
import { formatOrderBy, parseOrderBy } from "./orderBy";

describe("order by", () => {
  it("reads keys, directions and where the empty ones go", () => {
    expect(parseOrderBy("to_number(split_last(@.code, ',')) desc nulls first, @.id")).toEqual([
      { expr: "to_number(split_last(@.code, ','))", desc: true, nullsFirst: true },
      { expr: "@.id", desc: false, nullsFirst: false },
    ]);
    expect(parseOrderBy("rank DESC")).toEqual([{ expr: "rank", desc: true, nullsFirst: false }]);
    expect(parseOrderBy("")).toEqual([]);
    expect(parseOrderBy(null)).toEqual([]);
  });

  it("writes what it reads, with the defaults left out", () => {
    const text = "to_number(@.a) desc nulls first, @.b";
    expect(formatOrderBy(parseOrderBy(text))).toBe(text);
    expect(formatOrderBy([{ expr: "  ", desc: true, nullsFirst: false }])).toBe("");
  });
});
