import { describe, expect, it } from "vitest";
import { clampStep, padRect, placeCard, unionRect } from "./tour";

const view = { width: 1000, height: 700 };
const card = { width: 300, height: 150 };

describe("tour geometry", () => {
  it("puts the card on the preferred side when it fits, the arrow facing the target", () => {
    const p = placeCard({ left: 400, top: 100, width: 100, height: 40 }, card, view, "bottom");
    expect(p.arrow).toBe("top");
    expect(p.top).toBeGreaterThan(140);
    expect(p.left).toBe(450 - 150);
    expect(p.arrowAt).toBe(150);
  });

  it("goes to another side when the preferred one is out of the window", () => {
    const low = placeCard({ left: 400, top: 600, width: 100, height: 40 }, card, view, "bottom");
    expect(low.arrow).toBe("bottom"); // the card is above, its bottom edge faces the target
    expect(low.top + card.height).toBeLessThan(600);
    const wide = placeCard({ left: 0, top: 300, width: 900, height: 100 }, card, view, "right");
    expect(wide.arrow).not.toBe("left");
  });

  it("stays inside the window and keeps the arrow on the card", () => {
    const p = placeCard({ left: 980, top: 10, width: 20, height: 20 }, card, view, "bottom");
    expect(p.left + card.width).toBeLessThanOrEqual(view.width - 8);
    expect(p.arrowAt).toBeLessThanOrEqual(card.width - 18);
    expect(p.arrowAt).toBeGreaterThanOrEqual(18);
  });

  it("centres the card, without an arrow, when nothing is highlighted", () => {
    const p = placeCard(null, card, view);
    expect(p.arrow).toBeNull();
    expect(p.left).toBe(350);
  });

  it("clamps steps and pads rectangles", () => {
    expect([clampStep(-1, 5), clampStep(2, 5), clampStep(9, 5)]).toEqual([0, 2, 4]);
    expect(padRect({ left: 10, top: 10, width: 20, height: 20 }, 4)).toEqual({
      left: 6,
      top: 6,
      width: 28,
      height: 28,
    });
  });

  it("frames several parts with one rectangle", () => {
    expect(unionRect([])).toBeNull();
    expect(
      unionRect([
        { left: 10, top: 10, width: 100, height: 20 },
        { left: 20, top: 40, width: 50, height: 200 },
      ]),
    ).toEqual({ left: 10, top: 10, width: 100, height: 230 });
  });
});
