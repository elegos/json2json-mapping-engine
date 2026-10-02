// The quick tutorial: steps as data, and the geometry of the card beside the highlighted part.
import type { Book } from "./guideModel";

/** The state of the interface a step needs; the tour loads it, going forward or back, so a step
 * looks the same whenever it is reached. Anything left out is not touched. */
export interface TourState {
  view?: "rules" | "lookups" | "paths" | "golden" | "project";
  /** Id of the rule to select (`unit`, `cust.name`): its row is highlighted and the override
   * pane opens for it in Developer mode. */
  select?: string | null;
  developerMode?: boolean;
  showIds?: boolean;
  /** The function explorer panel. */
  explorer?: boolean;
}

export type Side = "top" | "bottom" | "left" | "right";

export interface TourStep {
  id: string;
  title: string;
  /** A short paragraph; a blank line starts another. */
  text: string;
  /** CSS selector of the part to highlight; without it the card sits in the middle. */
  target?: string;
  /** What the highlighted part is, for those who cannot see the frame around it. */
  label?: string;
  /** Preferred side of the target for the card. */
  side?: Side;
  state?: TourState;
}

export interface TourDef {
  id: Book;
  title: string;
  steps: TourStep[];
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface Placement {
  left: number;
  top: number;
  /** The side of the card that faces the target (where the arrow is); null = no arrow. */
  arrow: Side | null;
  /** Distance of the arrow from the card's start edge along that side. */
  arrowAt: number;
}

const GAP = 14;
const MARGIN = 8;
const ARROW_INSET = 18;

const OPPOSITE: Record<Side, Side> = { top: "bottom", bottom: "top", left: "right", right: "left" };

function candidate(target: Rect, card: Size, side: Side): { left: number; top: number } {
  const midX = target.left + target.width / 2;
  const midY = target.top + target.height / 2;
  switch (side) {
    case "bottom":
      return { left: midX - card.width / 2, top: target.top + target.height + GAP };
    case "top":
      return { left: midX - card.width / 2, top: target.top - card.height - GAP };
    case "right":
      return { left: target.left + target.width + GAP, top: midY - card.height / 2 };
    case "left":
      return { left: target.left - card.width - GAP, top: midY - card.height / 2 };
  }
}

const fits = (p: { left: number; top: number }, card: Size, view: Size) =>
  p.left >= MARGIN &&
  p.top >= MARGIN &&
  p.left + card.width <= view.width - MARGIN &&
  p.top + card.height <= view.height - MARGIN;

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, Math.max(lo, hi)));

/** Where the card goes: on the preferred side of the target if it fits the window, else on
 * another side, else the closest position inside the window. With no target it is centred. */
export function placeCard(
  target: Rect | null,
  card: Size,
  view: Size,
  preferred: Side = "bottom",
): Placement {
  if (!target) {
    return {
      left: (view.width - card.width) / 2,
      top: Math.max(MARGIN, (view.height - card.height) / 3),
      arrow: null,
      arrowAt: 0,
    };
  }
  const order: Side[] = [preferred, ...(["bottom", "top", "right", "left"] as Side[]).filter((s) => s !== preferred)];
  const side = order.find((s) => fits(candidate(target, card, s), card, view)) ?? preferred;
  const raw = candidate(target, card, side);
  const left = clamp(raw.left, MARGIN, view.width - card.width - MARGIN);
  const top = clamp(raw.top, MARGIN, view.height - card.height - MARGIN);
  const horizontal = side === "top" || side === "bottom";
  const along = horizontal
    ? target.left + target.width / 2 - left
    : target.top + target.height / 2 - top;
  const length = horizontal ? card.width : card.height;
  return {
    left,
    top,
    arrow: OPPOSITE[side],
    arrowAt: clamp(along, ARROW_INSET, length - ARROW_INSET),
  };
}

/** A step index kept inside the tour. */
export const clampStep = (index: number, count: number) => Math.max(0, Math.min(index, count - 1));

/** Growing a rectangle to leave some air around what it frames. */
export const padRect = (r: Rect, by: number): Rect => ({
  left: r.left - by,
  top: r.top - by,
  width: r.width + 2 * by,
  height: r.height + 2 * by,
});
