import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { TOURS } from "./tourSteps";

const fixture = readFileSync(
  new URL("../../fixtures/tour-project/mappings/functional/orders.fn.yaml", import.meta.url),
  "utf8",
);

describe("the tours", () => {
  for (const tour of Object.values(TOURS)) {
    it(`${tour.id}: unique step ids, text for each, a label where something is framed`, () => {
      const ids = tour.steps.map((s) => s.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const s of tour.steps) {
        expect(s.title && s.text, s.id).toBeTruthy();
        if (s.target) expect(s.label, `${s.id} names what it frames`).toBeTruthy();
      }
    });

    it(`${tour.id}: selects rules the tutorial project has`, () => {
      for (const s of tour.steps) {
        const id = s.state?.select;
        if (id) expect(fixture, `${s.id} selects ${id}`).toMatch(new RegExp(`^\\s+(- )?id: ${id}$`, "m"));
      }
    });
  }
});
