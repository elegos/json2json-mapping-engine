import { useEffect, useRef, useState } from "react";

interface Props {
  /** Adds a rule of this kind (`field`, `object`, `loop`). */
  onAdd: (kind: string) => void;
}

const KINDS: [string, string][] = [
  ["field", "Field"],
  ["object", "Object"],
  ["loop", "Loop"],
];

/** "+ Add ▾": the kinds of rule the toolbar adds, in one button. */
export function AddMenu({ onAdd }: Props) {
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
    <div className="output-input add-menu" ref={box}>
      <button aria-haspopup="menu" aria-expanded={open} title="Add a rule inside the selected one, or at the end" onClick={() => setOpen(!open)}>
        + Add ▾
      </button>
      {open && (
        <div className="output-menu add-menu-list" role="menu">
          {KINDS.map(([kind, label]) => (
            <button
              key={kind}
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onAdd(kind);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
