import { describe, expect, it } from "vitest";
import { PAGES } from "./guide";
import { BOOKS, parseFigure } from "./guideModel";

describe("the guide's pages", () => {
  const ids = new Set(PAGES.map((p) => p.id));

  it("has pages in every book", () => {
    for (const b of BOOKS) expect(PAGES.some((p) => p.book === b.id)).toBe(true);
  });

  it("links only to pages that exist", () => {
    for (const p of PAGES) {
      for (const m of p.body.matchAll(/\]\(page:([^)]+)\)/g)) {
        expect(ids.has(m[1]), `${p.id} links to ${m[1]}`).toBe(true);
      }
    }
  });

  it("has figures that read, with numbered callouts", () => {
    for (const p of PAGES) {
      for (const m of p.body.matchAll(/```figure\n([\s\S]*?)\n```/g)) {
        const figure = parseFigure(m[1]);
        expect(typeof figure, `${p.id}: ${figure}`).toBe("object");
        if (typeof figure === "object") {
          expect(figure.callouts.map((c) => c.n)).toEqual(figure.callouts.map((_, i) => i + 1));
        }
      }
    }
  });
});
