import { useEffect, useState } from "react";
import type { GoldenCase } from "./api";
import { GoldenEditor } from "./GoldenEditor";

interface Props {
  project: string;
  mapping: string;
  cases: GoldenCase[];
  onImport: () => void;
  onNew: () => void;
  /** Something unsaved in the editor. */
  onDirty: (dirty: boolean) => void;
  /** A file of a case was saved: reload the list. */
  onSaved: () => void;
  /** True to leave the case being edited (nothing unsaved, or the user agreed to lose it). */
  confirmLeave: () => Promise<boolean>;
  onRename: (name: string) => void;
  onDelete: (name: string) => void;
}

/** The golden cases of the open mapping: `tests/golden/<mapping>/<case>.input.json` with an
 * optional expected output and expected rule errors. What is loaded here is what CI runs. */
export function Golden({
  project,
  mapping,
  cases,
  onImport,
  onNew,
  onDirty,
  onSaved,
  confirmLeave,
  onRename,
  onDelete,
}: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  // a case renamed or deleted is no longer the one in the editor
  useEffect(() => {
    if (editing && !cases.some((c) => c.name === editing)) setEditing(null);
  }, [cases, editing]);
  const edit = async (name: string) => {
    if (name !== editing && editing !== null && !(await confirmLeave())) return;
    setEditing(name);
  };
  return (
    <div className="golden">
      <p className="config-help golden-help">
        Golden cases are an input and the output expected for it. They live in{" "}
        <code>tests/golden/{mapping}/</code> as <code>&lt;case&gt;.input.json</code>,{" "}
        <code>&lt;case&gt;.expected.json</code> and <code>&lt;case&gt;.expected_errors.json</code>; the
        tool names the files for you when you load them.
      </p>
      <div className="golden-bar">
        <button onClick={onImport}>Import a case…</button>
        <button onClick={onNew}>New case…</button>
        <button disabled title="Needs the Python backend (not available yet)">
          ▶ Execute all…
        </button>
      </div>
      {cases.length === 0 ? (
        <div className="empty">No golden cases for this mapping yet.</div>
      ) : (
        <table className="golden-table">
          <thead>
            <tr>
              <th>Case</th>
              <th>Input</th>
              <th>Expected output</th>
              <th>Expected errors</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.name} className={c.name === editing ? "current" : undefined}>
                <td className="golden-name">
                  <button className="link" title="Edit this case" onClick={() => void edit(c.name)}>
                    {c.name}
                  </button>
                </td>
                <td>✓</td>
                <td>{c.expected ? "✓" : <span className="golden-none">none</span>}</td>
                <td>{c.errors ? "✓" : <span className="golden-none">none</span>}</td>
                <td className="golden-actions">
                  <button disabled title="Run this case: needs the Python backend (not available yet)">
                    ▶
                  </button>
                  <button title="Rename…" onClick={() => onRename(c.name)}>
                    ✎
                  </button>
                  <button title="Delete…" onClick={() => onDelete(c.name)}>
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing && (
        <GoldenEditor
          project={project}
          mapping={mapping}
          name={editing}
          onDirty={onDirty}
          onSaved={onSaved}
          onClose={async () => {
            if (await confirmLeave()) setEditing(null);
          }}
        />
      )}
    </div>
  );
}
