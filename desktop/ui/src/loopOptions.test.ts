import { describe, expect, it } from "vitest";
import { loopOptionsSummary } from "./LoopOptions";

describe("loopOptionsSummary", () => {
  it("says nothing for a loop with no options", () => {
    expect(loopOptionsSummary({ kind: "loop", index_start: 0, order_by: null })).toBe("");
  });

  it("lists what is set, in a few words", () => {
    expect(
      loopOptionsSummary({ order_by: "@.sku desc", index_start: 1, when_empty: "omit", parallel: 4 }),
    ).toBe("ordered by @.sku desc, @index from 1, left out when empty, parallel 4");
    expect(loopOptionsSummary({ when_empty: "list" })).toBe("empty list when empty");
  });
});
