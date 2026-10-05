import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { type FunctionEntry, fnAdd, fnOverride, functionList } from "./api";
import { insertableColumn, insertIntoCellEditor, subscribeCellEditor } from "./cellEditor";
import { callOf, filterFunctions } from "./functionExplorer";
import { validFunctionName } from "./fnEditor";
import { Confirm } from "./Confirm";
import { FunctionEditor, type EditorControl } from "./FunctionEditor";
import { PromptDialog } from "./PromptDialog";

interface Props {
  project: string | null;
  /** Slid in; the panels stay mounted (and keep their state) while it is out. */
  open: boolean;
  onClose: () => void;
}

/** A panel beside the grid listing the functions a mapping can call: searchable, with the
 * signature and description of each, and an Insert button for the cell being edited. */
export function FunctionExplorer({ project, open, onClose }: Props) {
  const [all, setAll] = useState<FunctionEntry[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  // the file being edited: the panel widens to the left to hold the editor
  const [editing, setEditing] = useState<{ file: string; focus?: string; nonce: number } | null>(null);
  // what the editor says about its text, to ask before an action replaces it
  const control = useRef<EditorControl>({ dirty: false, save: async () => true });
  const [pending, setPending] = useState<(() => void) | null>(null);
  const [creating, setCreating] = useState(false);
  const [lastFile, setLastFile] = useState("functions");
  const canInsert = useSyncExternalStore(subscribeCellEditor, () => insertableColumn() !== null);

  const reload = () =>
    functionList(project).then(
      (list) => {
        setAll(list);
        setError("");
      },
      (e) => setError(String(e instanceof Error ? e.message : e)),
    );
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  const fail = (e: unknown) => setError(String(e instanceof Error ? e.message : e));
  const edit = (file: string, focus?: string) => {
    setLastFile(file);
    setEditing((was) => ({ file, focus, nonce: (was?.nonce ?? 0) + 1 }));
  };
  /** Runs `action`; with unsaved changes in the editor it first asks to save them. */
  const guarded = (action: () => void) => {
    if (editing && control.current.dirty) setPending(() => action);
    else action();
  };
  const override = (name: string) => {
    if (!project) return;
    fnOverride(project, name).then(async ({ file }) => {
      await reload();
      edit(file, name);
    }, fail);
  };
  const create = async (name: string, file: string) => {
    if (!project) return;
    try {
      await fnAdd(project, file, name);
      await reload();
      setChosen(name);
      edit(file, name);
    } catch (e) {
      fail(e);
    }
  };

  const shown = useMemo(() => filterFunctions(all, query), [all, query]);
  const current = shown.find((f) => f.name === chosen) ?? shown[0];

  return (
    <div className={`fx${open ? " open" : ""}${editing ? " editing" : ""}`}>
      <div className="fx-editor" aria-hidden={!editing}>
        {editing && project && (
          <FunctionEditor
            key="editor"
            project={project}
            file={editing.file}
            focus={editing.focus}
            nonce={editing.nonce}
            control={control}
            functions={all}
            onChanged={() => void reload()}
            onOpen={(file) => edit(file)}
            onClose={() => setEditing(null)}
          />
        )}
      </div>
      <aside className="explorer" aria-label="Function explorer">
      <div className="explorer-bar">
        <strong>Functions</strong>
        {project && (
          <button onClick={() => setCreating(true)} title="Add a function to a file of the project">
            New function…
          </button>
        )}
        <button onClick={onClose} aria-label="Close the function explorer">
          ✕
        </button>
      </div>
      <p className="explorer-about">
        What Source and Expression cells can call, and override code too, by the same names.
      </p>
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
            {current.targets.length > 0 && ` Written out for: ${current.targets.join(", ")}.`}
            {!current.python_code && (
              <span className="golden-doubt">
                {" "}
                No code for Python: a rule that calls it cannot run in the golden cases.
              </span>
            )}
          </p>
          <button
            className="primary"
            disabled={!canInsert}
            title={
              canInsert
                ? "Put the call in the cell or the override being edited"
                : "Edit a Source or Expression cell, or a rule's override, first"
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
          {project && !current.builtin && (
            <button
              onClick={() =>
                guarded(() => edit(current.origin.replace(/^fn\//, "").replace(/\.fn$/, ""), current.name))
              }
              title="Edit the file this function is in"
            >
              Edit…
            </button>
          )}
          {project && current.builtin && (
            <button
              onClick={() => guarded(() => override(current.name))}
              title="Copy it into fn/builtin_overrides.fn and edit the copy"
            >
              Override…
            </button>
          )}
        </div>
      )}
      </aside>
      {pending && (
        <Confirm
          message="The open file has changes that are not saved."
          choices={[
            { id: "save", label: "Save and continue", primary: true },
            { id: "cancel", label: "Cancel" },
          ]}
          onChoose={(id) => {
            const action = pending;
            setPending(null);
            if (id === "save") void control.current.save().then((saved) => saved && action());
          }}
        />
      )}
      {creating && project && (
        <PromptDialog
          title="New function"
          confirm="Create"
          fields={[
            { key: "name", label: "Function name", value: "" },
            { key: "file", label: "In file", value: lastFile, hint: "fn/<file>.fn; made when it does not exist" },
          ]}
          validate={({ name, file }) =>
            validFunctionName(name) ??
            (all.some((f) => f.name === name) ? "a function with that name exists" : null) ??
            (/^[A-Za-z][A-Za-z0-9_-]*$/.test(file) ? null : "the file: letters, digits, _ and -")
          }
          onDone={(values) => {
            setCreating(false);
            if (values) guarded(() => void create(values.name, values.file));
          }}
        />
      )}
    </div>
  );
}
