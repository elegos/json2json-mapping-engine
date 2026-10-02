import { describe, expect, it } from "vitest";
import { proposeName } from "./GoldenImport";

describe("proposeName", () => {
  it("takes the file's name without its folder, .json and .input", () => {
    expect(proposeName("/home/me/data/two_lines.input.json")).toBe("two_lines");
    expect(proposeName("C:\\x\\Order 17.json")).toBe("Order_17");
  });
  it("leaves nothing odd at the ends", () => {
    expect(proposeName("/x/(copy) a.b.json")).toBe("copy_a_b");
    expect(proposeName("/x/.json")).toBe("");
  });
});
