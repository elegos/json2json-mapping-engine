import { useCallback, useEffect, useState } from "react";
import {
  type SharedLookup,
  sharedLookupDelete,
  sharedLookups,
  sharedLookupSave,
} from "./api";
import {
  addEntry,
  type Diagnostic,
  type FunctionalFile,
  type LookupRule,
  lookups,
  parseTyped,
  renameEntry,
  showValue,
} from "./model";
import { markedMessage, readersText, sharedChanged } from "./sharedLookups";

interface Props {
  tree: FunctionalFile;
  project: string;
  diagnostics: ReadonlyMap<string, Diagnostic[]>;
  onEdit: (path: string, change: (rule: LookupRule) => void) => void;
  onAdd: () => void;
  onDelete: (path: string) => void;
  /** Moves the lookup at `path` of the mapping into the project (asks first). */
  onShare: (label: string) => void;
  /** Gives each mapping that reads the project-wide lookup its own copy (asks first). */
  onUnshare: (label: string) => void;
  /** Before the project's files change under the mapping: true when it is fine to go on. */
  beforeDiskChange: () => Promise<boolean>;
  /** After they changed: the mapping is read again. */
  afterDiskChange: (message: string) => Promise<void>;
  /** Bumped by the app when a lookup was moved to or from the project, to list them again. */
  version: number;
}

const TYPES = ["str", "int", "number", "bool", "date", "datetime"];

interface Table {
  label: string;
  type: string | null;
  description: string | null;
  entries: Record<string, unknown>;
}

interface TableEditorProps {
  table: Table;
  /** A project-wide table is named once, when it is created. */
  labelEditable: boolean;
  issues: Diagnostic[];
  onChange: (change: (t: Table) => void) => void;
}

/** The label, type, description and key / value table of one lookup. */
function TableEditor({ table, labelEditable, issues, onChange }: TableEditorProps) {
  return (
    <>
      <div className="lookup-head">
        <label>
          Label
          <input
            value={table.label}
            readOnly={!labelEditable}
            onChange={(e) => onChange((t) => (t.label = e.target.value))}
          />
        </label>
        <label>
          Type
          <select
            value={table.type ?? ""}
            onChange={(e) => onChange((t) => (t.type = e.target.value || null))}
          >
            <option value="">(not declared)</option>
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          Description
          <input
            value={table.description ?? ""}
            onChange={(e) => onChange((t) => (t.description = e.target.value || null))}
          />
        </label>
      </div>
      {issues.map((d, i) => (
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
          {Object.entries(table.entries).map(([key, value]) => (
            <tr key={key}>
              <td>
                <input
                  defaultValue={key}
                  onBlur={(e) =>
                    onChange((t) => {
                      t.entries = renameEntry(t.entries, key, e.target.value);
                    })
                  }
                />
              </td>
              <td>
                <input
                  key={showValue(value)}
                  defaultValue={showValue(value)}
                  title={
                    table.type
                      ? `Every value is a ${table.type}`
                      : 'No type declared: numbers, true, false and null keep their type; quote ("1") to force a string'
                  }
                  onBlur={(e) =>
                    onChange((t) => {
                      t.entries = { ...t.entries, [key]: parseTyped(e.target.value, table.type) };
                    })
                  }
                />
              </td>
              <td>
                <button
                  title="Delete entry"
                  onClick={() =>
                    onChange((t) => {
                      t.entries = Object.fromEntries(
                        Object.entries(t.entries).filter(([k]) => k !== key),
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
      <button onClick={() => onChange((t) => (t.entries = addEntry(t.entries)))}>+ Entry</button>
    </>
  );
}

const WIDE_HELP =
  "A project-wide lookup is kept once in the project (lookups/) and read as @label by any mapping. " +
  "Use it for a table that hardly changes and several mappings need.";

/** The lookups of the mapping (a list on the left, the selected one's key / value table on the
 * right) and, under them, the project-wide ones. Referenced from expressions as `@label`. */
export function Lookups({
  tree,
  project,
  diagnostics,
  onEdit,
  onAdd,
  onDelete,
  onShare,
  onUnshare,
  beforeDiskChange,
  afterDiskChange,
  version,
}: Props) {
  const all = lookups(tree.rules);
  const [picked, setPicked] = useState<string | null>(null);
  const [wide, setWide] = useState<SharedLookup[]>([]);
  const [pickedWide, setPickedWide] = useState<string | null>(null);
  // the project-wide table being edited, and the new one being made
  const [draft, setDraft] = useState<Table | null>(null);
  const [creating, setCreating] = useState(false);
  const [note, setNote] = useState("");

  const refresh = useCallback(async () => {
    try {
      setWide(await sharedLookups(project));
    } catch (e) {
      setNote(String(e instanceof Error ? e.message : e));
    }
  }, [project]);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `version` is a signal to list again
  useEffect(() => void refresh(), [refresh, version]);

  const currentWide = creating ? null : wide.find((w) => w.label === pickedWide);
  const current = pickedWide || creating ? undefined : (all.find((l) => l.path === picked) ?? all[0]);
  // the draft follows the table picked, and is dropped with it
  useEffect(() => {
    if (creating) return;
    setDraft(currentWide ? { ...currentWide, entries: { ...currentWide.entries } } : null);
    setNote("");
  }, [currentWide, creating]);

  const pickLocal = (path: string) => {
    setPicked(path);
    setPickedWide(null);
    setCreating(false);
  };
  const pickWide = (label: string) => {
    setPickedWide(label);
    setCreating(false);
  };
  const startCreating = () => {
    setCreating(true);
    setPickedWide(null);
    setDraft({ label: "", type: "str", description: null, entries: { key: "value" } });
    setNote("");
  };

  const changed = draft && (creating || (currentWide && sharedChanged(currentWide, draft)));
  const save = async () => {
    if (!draft) return;
    if (!(await beforeDiskChange())) return;
    try {
      const marked = await sharedLookupSave(project, draft, creating);
      setCreating(false);
      setPickedWide(draft.label);
      await refresh();
      await afterDiskChange(markedMessage(draft.label, marked));
    } catch (e) {
      setNote(String(e instanceof Error ? e.message : e));
    }
  };
  const remove = async () => {
    if (!currentWide || !(await beforeDiskChange())) return;
    try {
      await sharedLookupDelete(project, currentWide.label);
      setPickedWide(null);
      await refresh();
      await afterDiskChange(`@${currentWide.label} deleted`);
    } catch (e) {
      setNote(String(e instanceof Error ? e.message : e));
    }
  };

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
              onClick={() => pickLocal(l.path)}
            >
              {issues.length ? "⚠️ " : ""}@{l.rule.label}
            </div>
          );
        })}
        {all.length === 0 && <div className="empty">No lookups in this mapping</div>}
        <div className="lookup-section" title={WIDE_HELP}>
          Project wide
        </div>
        <div className="toolbar">
          <button onClick={startCreating} title={WIDE_HELP}>
            + Project lookup
          </button>
        </div>
        {wide.map((w) => (
          <div
            key={w.label}
            className={w.label === pickedWide && !creating ? "file current" : "file"}
            title={readersText(w)}
            onClick={() => pickWide(w.label)}
          >
            @{w.label}
            {w.label in tree.shared && w.used_by.length > 1 ? ` · ${w.used_by.length} mappings` : ""}
          </div>
        ))}
        {wide.length === 0 && <div className="empty">None in this project</div>}
      </div>
      {current && (
        <div className="lookup-detail" key={current.path}>
          <TableEditor
            table={{ ...current.rule, description: current.rule.description ?? null }}
            labelEditable
            issues={diagnostics.get(current.path) ?? []}
            onChange={(change) => onEdit(current.path, (r) => change(r))}
          />
          <label className="wide-flag" title={WIDE_HELP}>
            <input type="checkbox" checked={false} onChange={() => onShare(current.rule.label)} />
            Project wide: keep this table in the project, for every mapping to read
          </label>
        </div>
      )}
      {draft && (creating || currentWide) && (
        <div className="lookup-detail" key={creating ? "new" : currentWide?.label}>
          {currentWide && <p className="lookup-readers">{readersText(currentWide)}</p>}
          <TableEditor table={draft} labelEditable={creating} issues={[]} onChange={(change) => setDraft((d) => (d ? (change(d), { ...d }) : d))} />
          {note && <div className="lookup-issue error">{note}</div>}
          <div className="toolbar">
            <button disabled={!changed || (creating && !draft.label)} onClick={() => void save()}>
              {creating ? "Create" : `Save${changed ? " ●" : ""}`}
            </button>
            <button
              disabled={!changed}
              onClick={() =>
                creating ? setCreating(false) : setDraft(currentWide ? { ...currentWide, entries: { ...currentWide.entries } } : null)
              }
            >
              {creating ? "Cancel" : "Revert"}
            </button>
            {currentWide && <button onClick={() => void remove()}>Delete</button>}
          </div>
          {currentWide && (
            <>
              <p className="lookup-note">
                Saving a change sends the rules that read this table back to review in every
                mapping, with a note saying what changed.
              </p>
              <label className="wide-flag" title={WIDE_HELP}>
                <input type="checkbox" checked onChange={() => onUnshare(currentWide.label)} />
                Project wide: clear to give each mapping that reads it its own copy
              </label>
            </>
          )}
        </div>
      )}
    </div>
  );
}
