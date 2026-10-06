import { useEffect, useRef, useState } from "react";
import type { GoldenResult } from "./api";
import { runReport } from "./runReport";

interface Props {
  result: GoldenResult | null;
  /** Saves the mapped JSON (the output of the run) where the user chooses. */
  onDownload: () => void;
  /** Takes the grid to the rule at this path and selects its Source. */
  onShowRule: (path: string) => void;
}

/** What the last run of the mapping gave: "No errors", or the number of rules that failed (a click
 * lists them with their cause; a click on one goes to its rule), and the button that saves the
 * mapped JSON. */
export function RunReport({ result, onDownload, onShowRule }: Props) {
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
  if (!result) return null;
  const report = runReport(result);
  return (
    <div className="run-report" ref={box}>
      <button
        className={`schema-button ${report.ok ? "ok" : "invalid"}`}
        title={report.ok ? "The mapping ran on this input without any rule failing" : "Show the rules that failed"}
        onClick={() => !report.ok && setOpen(!open)}
        aria-haspopup={report.ok ? undefined : "menu"}
      >
        <span className={`light ${report.ok ? "ok" : "invalid"}`} />
        {report.label}
      </button>
      {open && (
        <div className="output-menu run-report-list" role="list">
          {report.lines.map((line, i) => {
            const path = report.paths[i];
            return path ? (
              <button
                key={line}
                role="listitem"
                title="Go to this rule"
                onClick={() => {
                  setOpen(false);
                  onShowRule(path);
                }}
              >
                {line}
              </button>
            ) : (
              <div key={line} role="listitem">
                {line}
              </div>
            );
          })}
        </div>
      )}
      <button title="Save the output of this run as a JSON file" onClick={onDownload}>
        Download mapped JSON
      </button>
    </div>
  );
}
