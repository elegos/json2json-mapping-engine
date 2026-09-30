import { useState } from "react";
import {
  addEntry,
  type Diagnostic,
  type FunctionalFile,
  type LookupRule,
  lookups,
  parseValue,
  renameEntry,
  showValue,
} from "./model";

interface Props {
  tree: FunctionalFile;
  diagnostics: ReadonlyMap<string, Diagnostic[]>;
  onEdit: (path: string, change: (rule: LookupRule) => void) => void;
  onAdd: () => void;
  onDelete: (path: string) => void;
}

/** The lookup rules of the file: a list on the left, the selected one's key/value table
 * on the right. Referenced from expressions as `@label`. */
export function Lookups({ tree, diagnostics, onEdit, onAdd, onDelete }: Props) {
  const all = lookups(tree.rules);
  const [picked, setPicked] = useState<string | null>(null);
  const current = all.find((l) => l.path === picked) ?? all[0];

  return (
    <div className="lookups">
      <div className="lookup-list">
        <div className="toolbar">
          <button onClick={onAdd}>+ Lookup</button>
          <button disabled={!current} onClick={() => current && onDelete(current.path)}>
            Delete
          </button>
        </div>
        {all.map((l) => {
          const issues = diagnostics.get(l.path) ?? [];
          return (
            <div
              key={l.path}
              className={l === current ? "file current" : "file"}
              title={issues.map((d) => d.message).join("\n")}
              onClick={() => setPicked(l.path)}
            >
              {issues.length ? "⚠️ " : ""}@{l.rule.label}
            </div>
          );
        })}
        {all.length === 0 && <div className="empty">No lookups</div>}
      </div>
      {current && (
        <div className="lookup-detail" key={current.path}>
          <div className="lookup-head">
            <label>
              Label
              <input
                value={current.rule.label}
                onChange={(e) => onEdit(current.path, (r) => (r.label = e.target.value))}
              />
            </label>
            <label className="grow">
              Description
              <input
                value={current.rule.description ?? ""}
                onChange={(e) =>
                  onEdit(current.path, (r) => (r.description = e.target.value || null))
                }
              />
            </label>
          </div>
          {(diagnostics.get(current.path) ?? []).map((d, i) => (
            <div key={i} className={`lookup-issue ${d.severity}`}>
              {d.message}
            </div>
          ))}
          <table>
            <thead>
              <tr>
                <th>Key</th>
                <th>Value</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {Object.entries(current.rule.entries).map(([key, value]) => (
                <tr key={key}>
                  <td>
                    <input
                      defaultValue={key}
                      onBlur={(e) =>
                        onEdit(current.path, (r) => {
                          r.entries = renameEntry(r.entries, key, e.target.value);
                        })
                      }
                    />
                  </td>
                  <td>
                    <input
                      key={showValue(value)}
                      defaultValue={showValue(value)}
                      title='Numbers, true, false and null keep their type; quote ("1") to force a string'
                      onBlur={(e) =>
                        onEdit(current.path, (r) => {
                          r.entries = { ...r.entries, [key]: parseValue(e.target.value) };
                        })
                      }
                    />
                  </td>
                  <td>
                    <button
                      title="Delete entry"
                      onClick={() =>
                        onEdit(current.path, (r) => {
                          r.entries = Object.fromEntries(
                            Object.entries(r.entries).filter(([k]) => k !== key),
                          );
                        })
                      }
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={() => onEdit(current.path, (r) => (r.entries = addEntry(r.entries)))}>
            + Entry
          </button>
        </div>
      )}
    </div>
  );
}
