import { describe, expect, it } from "vitest";
import { markedMessage, readersText, sharedChanged } from "./sharedLookups";

describe("project-wide lookups", () => {
  it("says what a change did to the rules that read the table", () => {
    expect(markedMessage("fx", {})).toBe("@fx saved");
    expect(markedMessage("fx", { orders: ["cur"] })).toBe(
      "@fx saved; 1 rule in 1 mapping (orders) back to review, with a note saying what changed",
    );
    expect(markedMessage("fx", { orders: ["a", "b"], positions: ["c"] })).toContain(
      "3 rules in 2 mappings (orders, positions)",
    );
  });

  it("says who reads a table", () => {
    expect(readersText({ used_by: [] })).toBe("No mapping reads it yet.");
    expect(readersText({ used_by: ["a", "b"] })).toBe("Read by a, b.");
  });

  it("tells a changed draft from the saved table", () => {
    const saved = { type: "str", description: null, entries: { IT: "EUR" } };
    expect(sharedChanged(saved, { ...saved, description: "" })).toBe(false);
    expect(sharedChanged(saved, { ...saved, entries: { IT: "USD" } })).toBe(true);
    expect(sharedChanged(saved, { ...saved, type: null })).toBe(true);
  });
});
