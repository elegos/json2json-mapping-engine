import { useEffect, useRef, useState } from "react";

interface Props {
  recent: string[];
  onOpen: () => void;
  onPick: (dir: string) => void;
}

/** "Open project…" with a caret sub-button that lists the recent projects below the whole control. */
export function ProjectButton({ recent, onOpen, onPick }: Props) {
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
      <button className="split-main" onClick={onOpen}>
        Open project…
      </button>
      <button
        className="split-caret"
        aria-label="Recent projects"
        aria-expanded={open}
        disabled={recent.length === 0}
        onClick={() => setOpen(!open)}
      >
        ▼
      </button>
      {open && (
        <ul className="split-menu">
          {recent.map((dir) => (
            <li
              key={dir}
              title={dir}
              onClick={() => {
                setOpen(false);
                onPick(dir);
              }}
            >
              {dir}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
