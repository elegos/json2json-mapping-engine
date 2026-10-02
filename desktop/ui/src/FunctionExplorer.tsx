import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { type FunctionEntry, functionList } from "./api";
import { insertableColumn, insertIntoCellEditor, subscribeCellEditor } from "./cellEditor";
import { callOf, filterFunctions } from "./functionExplorer";

interface Props {
  project: string | null;
  onClose: () => void;
}

/** A panel beside the grid listing the functions a mapping can call: searchable, with the
 * signature and description of each, and an Insert button for the cell being edited. */
export function FunctionExplorer({ project, onClose }: Props) {
  const [all, setAll] = useState<FunctionEntry[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const canInsert = useSyncExternalStore(subscribeCellEditor, () => insertableColumn() !== null);

  useEffect(() => {
    functionList(project).then(
      (list) => {
        setAll(list);
        setError("");
      },
      (e) => setError(String(e instanceof Error ? e.message : e)),
    );
  }, [project]);

  const shown = useMemo(() => filterFunctions(all, query), [all, query]);
  const current = shown.find((f) => f.name === chosen) ?? shown[0];

  return (
    <aside className="explorer" aria-label="Function explorer">
      <div className="explorer-bar">
        <strong>Functions</strong>
        <button onClick={onClose} aria-label="Close the function explorer">
          ✕
        </button>
      </div>
      <input
        className="explorer-search"
        placeholder="Search functions"
        value={query}
        spellCheck={false}
        onChange={(e) => setQuery(e.target.value)}
      />
      {error && <p className="wizard-error">{error}</p>}
      <ul className="explorer-list" aria-label="Functions">
        {shown.length === 0 && <li className="empty">No function matches.</li>}
        {shown.map((f) => (
          <li key={f.name}>
            <button
              className={f.name === current?.name ? "current" : undefined}
              onClick={() => setChosen(f.name)}
            >
              <span>{f.signature}</span>
              <small>{f.builtin ? "built-in" : f.origin}</small>
            </button>
          </li>
        ))}
      </ul>
      {current && (
        <div className="explorer-detail">
          <code>
            {current.signature}
            {current.returns ? ` → ${current.returns}` : ""}
          </code>
          <p>{current.doc || "No description."}</p>
          <dl>
            {current.params.map((p) => (
              <div key={p.name}>
                <dt>{p.variadic ? `*${p.name}` : p.name}</dt>
                <dd>
                  {p.annotation || "any"}
                  {p.default !== null ? ` = ${p.default}` : ""}
                </dd>
              </div>
            ))}
          </dl>
          <p className="explorer-origin">
            {current.builtin ? "Built-in." : `Project function, in ${current.origin}.`}
            {current.replaces_builtin && " It replaces the built-in of the same name."}
          </p>
          <button
            className="primary"
            disabled={!canInsert}
            title={
              canInsert
                ? "Put the call in the cell being edited"
                : "Edit a Source or Expression cell first"
            }
            // keep the focus in the cell, or the edit ends before the call is inserted
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              const { call, first } = callOf(current);
              insertIntoCellEditor(call, first);
            }}
          >
            Insert
          </button>
        </div>
      )}
    </aside>
  );
}
