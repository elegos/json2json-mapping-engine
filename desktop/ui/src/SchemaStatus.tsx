import type { ReactNode } from "react";
import type { SchemaKind, SchemasStatus } from "./api";

interface Props {
  status: SchemasStatus | null;
  onPick: (kind: SchemaKind) => void;
  /** More buttons of the same kind, before the schemas'. */
  children?: ReactNode;
}

const LABELS: [SchemaKind, string][] = [
  ["input", "Input schema"],
  ["output", "Output schema"],
];

/** Two status buttons: is the mapping's input / output JSON Schema loaded? A click opens the
 * file picker to load it, or to load another in its place. */
export function SchemaStatusButtons({ status, onPick, children }: Props) {
  return (
    <div className="schema-status">
      {children}
      {LABELS.map(([kind, label]) => {
        const s = status?.[kind];
        const state = s?.state ?? "unknown";
        const title = !s
          ? "Checking…"
          : s.state === "ok"
            ? `${s.path}\nClick to load another`
            : `${s.reason ?? "not loaded"} (${s.path})\nClick to load it`;
        return (
          <button key={kind} className={`schema-button ${state}`} title={title} onClick={() => onPick(kind)}>
            <span className={`light ${state}`} />
            {label}
          </button>
        );
      })}
    </div>
  );
}
