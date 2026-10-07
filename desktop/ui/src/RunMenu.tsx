import { useEffect, useRef, useState } from "react";

interface Props {
  disabled: boolean;
  /** The steps the caret lists (the developer's); empty = only the main button. */
  steps: { id: string; label: string; title: string }[];
  onRun: (step: string) => void;
}

/** "Check…" with a caret listing the other steps of the pipeline (Transpile, Build, Publish). */
export function RunMenu({ disabled, steps, onRun }: Props) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className="split" ref={box}>
      <button className="split-main" disabled={disabled} title="Transpile, compile and compare with the committed files" onClick={() => onRun("check")}>
        Check…
      </button>
      {steps.length > 0 && (
        <button className="split-caret" aria-label="Other steps" aria-expanded={open} disabled={disabled} onClick={() => setOpen(!open)}>
          ▼
        </button>
      )}
      {open && (
        <ul className="split-menu" role="menu">
          {steps.map((s) => (
            <li
              key={s.id}
              role="menuitem"
              title={s.title}
              onClick={() => {
                setOpen(false);
                onRun(s.id);
              }}
            >
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
