import type { GoldenCase } from "./api";

interface Props {
  mapping: string;
  cases: GoldenCase[];
  onImport: () => void;
  onRename: (name: string) => void;
  onDelete: (name: string) => void;
}

/** The golden cases of the open mapping: `tests/golden/<mapping>/<case>.input.json` with an
 * optional expected output and expected rule errors. What is loaded here is what CI runs. */
export function Golden({ mapping, cases, onImport, onRename, onDelete }: Props) {
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
              <tr key={c.name}>
                <td className="golden-name">{c.name}</td>
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
    </div>
  );
}
