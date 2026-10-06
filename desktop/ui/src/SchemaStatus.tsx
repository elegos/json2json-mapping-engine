import { useEffect, useRef, useState, type ReactNode } from "react";
import type { SchemaKind, SchemasStatus } from "./api";

interface Props {
  status: SchemasStatus | null;
  /** Load a schema from a file picked outside the project. */
  onPick: (kind: SchemaKind) => void;
  /** Load one of the project's own schemas (a path from the project root). */
  onUse: (kind: SchemaKind, file: string) => void;
  /** The schema files in the project's `schemas/`. */
  listFiles: () => Promise<string[]>;
  /** Lay out the rules the output schema describes, again (only the missing ones are added). */
  onScaffold: () => void;
  /** More buttons of the same kind, before the schemas'. */
  children?: ReactNode;
}

const LABELS: [SchemaKind, string][] = [
  ["input", "Input schema"],
  ["output", "Output schema"],
];

/** Two status buttons: is the mapping's input / output JSON Schema loaded? The light says so; a
 * click opens a menu to load it (from a file, or one of the project's schemas), or to load another
 * in its place, and, for the output schema, to lay out its rules again. */
export function SchemaStatusButtons({ status, onPick, onUse, listFiles, onScaffold, children }: Props) {
  const [open, setOpen] = useState<SchemaKind | null>(null);
  const [files, setFiles] = useState<string[] | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(null);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const toggle = (kind: SchemaKind) => {
    if (open === kind) return setOpen(null);
    setOpen(kind);
    setFiles(null);
    listFiles().then(setFiles, () => setFiles([]));
  };
  const choose = (run: () => void) => {
    setOpen(null);
    run();
  };

  return (
    <div className="schema-status" ref={box}>
      {children}
      {LABELS.map(([kind, label]) => {
        const s = status?.[kind];
        const state = s?.state ?? "unknown";
        const title = !s ? "Checking…" : s.state === "ok" ? s.path : `${s.reason ?? "not loaded"} (${s.path})`;
        // the mapping's own copy is not offered to itself
        const others = (files ?? []).filter((f) => f !== s?.path);
        return (
          <div className="output-input" key={kind}>
            <button
              className={`schema-button ${state}`}
              title={title}
              aria-haspopup="menu"
              aria-expanded={open === kind}
              onClick={() => toggle(kind)}
            >
              <span className={`light ${state}`} />
              {label}
            </button>
            {open === kind && (
              <div className="output-menu" role="menu">
                <button role="menuitem" onClick={() => choose(() => onPick(kind))}>
                  Load from a file…
                </button>
                <div className="output-group">From the project</div>
                {files === null && <div className="output-group">Looking…</div>}
                {files !== null && others.length === 0 && <div className="output-group">No other schema</div>}
                {others.map((f) => (
                  <button key={f} role="menuitem" title={f} onClick={() => choose(() => onUse(kind, f))}>
                    {f.replace(/^schemas\//, "")}
                  </button>
                ))}
                {kind === "output" && (
                  <>
                    <div className="output-group">Rules</div>
                    <button
                      role="menuitem"
                      disabled={s?.state !== "ok"}
                      title="Add the rules the schema describes that the mapping does not have yet; none is changed or deleted"
                      onClick={() => choose(onScaffold)}
                    >
                      Lay out the rules again
                    </button>
                  </>
                )}
                <div className="output-group">{s?.state === "ok" ? "Loaded" : "Not loaded"}</div>
                <div className="muted output-path" title={title}>
                  {title}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
