import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  clampStep,
  padRect,
  placeCard,
  type Placement,
  type Rect,
  type TourDef,
  type TourState,
  unionRect,
} from "./tour";

interface Props {
  tour: TourDef;
  index: number;
  onIndex: (index: number) => void;
  onClose: () => void;
  /** Puts the interface in the state a step needs; resolves when it is drawn. */
  apply: (state: TourState | undefined) => Promise<void>;
}

const FRAME = 4;

/** Waits for `selector` to be in the page (a state just loaded may still be drawing). */
async function find(selector: string, signal: { stale: boolean }): Promise<Element | null> {
  for (let i = 0; i < 30 && !signal.stale; i++) {
    const found = document.querySelector(selector);
    if (found) return found;
    await new Promise((r) => setTimeout(r, 50));
  }
  return null;
}

const rectOf = (el: Element): Rect => {
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width, height: r.height };
};

/**
 * The quick tutorial: a read-only, linear walk through the interface. Everything outside the
 * card is blocked while it runs; each step loads the state it needs, frames a part of the
 * window and says what it is. Back / Next / Close; Esc closes, the arrows move.
 */
export function Tour({ tour, index, onIndex, onClose, apply }: Props) {
  const step = tour.steps[clampStep(index, tour.steps.length)];
  const last = index >= tour.steps.length - 1;
  const card = useRef<HTMLDivElement>(null);
  const [target, setTarget] = useState<Rect | null>(null);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [ready, setReady] = useState(false);
  const elements = useRef<Element[]>([]);

  // load the step's state, then frame its target
  useEffect(() => {
    const signal = { stale: false };
    setReady(false);
    void (async () => {
      await apply(step.state);
      const wanted = step.target ? [step.target].flat() : [];
      const found = (await Promise.all(wanted.map((sel) => find(sel, signal)))).filter(
        (el): el is Element => el !== null,
      );
      if (signal.stale) return;
      elements.current = found;
      found[0]?.scrollIntoView({ block: "nearest", inline: "nearest" });
      setTarget(unionRect(found.map(rectOf)));
      setReady(true);
    })();
    return () => {
      signal.stale = true;
    };
    // the step, not the callback's identity
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step.id]);

  // the window may be resized (or the part move) while a step is shown
  useEffect(() => {
    const follow = () => setTarget(unionRect(elements.current.map(rectOf)));
    window.addEventListener("resize", follow);
    return () => window.removeEventListener("resize", follow);
  }, []);

  useLayoutEffect(() => {
    const box = card.current;
    if (!box || !ready) return;
    setPlacement(
      placeCard(
        target && padRect(target, FRAME),
        { width: box.offsetWidth, height: box.offsetHeight },
        { width: window.innerWidth, height: window.innerHeight },
        step.side,
      ),
    );
  }, [target, ready, step]);

  const go = useCallback(
    (to: number) => {
      if (to < 0) return;
      if (to >= tour.steps.length) onClose();
      else onIndex(to);
    },
    [tour.steps.length, onIndex, onClose],
  );

  // nothing outside the card gets a key while the tour runs; the card's own keys move it
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const inside = card.current?.contains(e.target as Node) ?? false;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        e.stopPropagation();
        go(index + 1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        e.stopPropagation();
        go(index - 1);
      } else if (e.key === "Tab" && card.current) {
        // keep the focus in the card
        const buttons = [...card.current.querySelectorAll<HTMLElement>("button:not(:disabled)")];
        const at = buttons.indexOf(document.activeElement as HTMLElement);
        const next = e.shiftKey ? at - 1 : at + 1;
        e.preventDefault();
        e.stopPropagation();
        buttons[(next + buttons.length) % buttons.length]?.focus();
      } else if (!inside) {
        e.stopPropagation();
        if (e.key !== "F5" && e.key !== "F12") e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [go, index, onClose]);

  // the focus goes into the card, and back where it was when the tour ends
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    return () => before?.focus?.();
  }, []);
  useEffect(() => {
    if (ready) card.current?.querySelector<HTMLElement>("button.primary")?.focus();
  }, [ready, step.id]);

  const frame = target && padRect(target, FRAME);
  return (
    <div className="tour" data-ready={ready}>
      <div className="tour-block" onMouseDown={(e) => e.preventDefault()} />
      {frame ? (
        <div
          className="tour-frame"
          style={{ left: frame.left, top: frame.top, width: frame.width, height: frame.height }}
        />
      ) : (
        <div className="tour-dim" />
      )}
      <div
        ref={card}
        className={`tour-card${placement?.arrow ? ` arrow-${placement.arrow}` : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-text"
        style={{
          left: placement?.left ?? 0,
          top: placement?.top ?? 0,
          visibility: placement ? "visible" : "hidden",
          ["--arrow-at" as string]: `${placement?.arrowAt ?? 0}px`,
        }}
      >
        <div className="tour-count">
          {tour.title} · {index + 1} of {tour.steps.length}
        </div>
        <h3 id="tour-title">{step.title}</h3>
        <div id="tour-text">
          {step.text.split(/\n\s*\n/).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
        {step.label && target && <span className="sr-only">Highlighted: {step.label}.</span>}
        <div className="tour-buttons">
          <button onClick={onClose}>Close</button>
          <span className="spacer" />
          <button disabled={index === 0} onClick={() => go(index - 1)}>
            Back
          </button>
          <button className="primary" onClick={() => go(index + 1)}>
            {last ? "Finish" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
