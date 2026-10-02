import type { Book } from "./guideModel";
import { useEffect, useRef, useState } from "react";

interface Props {
  onGuide: () => void;
  onExplorer: () => void;
  onTour: (book: Book) => void;
}

/** The "?" at the right of the toolbar: the guide and, later, the quick tutorials. */
export function HelpMenu({ onGuide, onExplorer, onTour }: Props) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div className="split" ref={box}>
      <button data-tour="help" aria-label="Help" aria-expanded={open} title="Help" onClick={() => setOpen(!open)}>
        ?
      </button>
      {open && (
        <ul className="split-menu help-menu">
          <li
            onClick={() => {
              setOpen(false);
              onGuide();
            }}
          >
            Guide
          </li>
          <li
            onClick={() => {
              setOpen(false);
              onExplorer();
            }}
          >
            Function explorer
          </li>
          <li
            onClick={() => {
              setOpen(false);
              onTour("functional");
            }}
          >
            Quick tour
          </li>
          <li
            onClick={() => {
              setOpen(false);
              onTour("developer");
            }}
          >
            Developer tour
          </li>
        </ul>
      )}
    </div>
  );
}
