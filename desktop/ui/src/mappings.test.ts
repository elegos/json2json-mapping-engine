import { describe, expect, it } from "vitest";
import { nameProblem } from "./mappings";

describe("nameProblem", () => {
  it("accepts identifiers", () => {
    expect(nameProblem("orders_2", [])).toBeNull();
    expect(nameProblem("_x", [])).toBeNull();
  });
  it("refuses empty names, odd characters and a leading digit", () => {
    expect(nameProblem("", [])).toMatch(/name/);
    for (const bad of ["1a", "a-b", "a b", "à"]) expect(nameProblem(bad, [])).toMatch(/Letters/);
  });
  it("refuses a name already taken", () => {
    expect(nameProblem("orders", ["orders", "x"])).toMatch(/already/);
  });
});
