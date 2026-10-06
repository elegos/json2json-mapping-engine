import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { type FunctionEntry, fnAdd, fnFiles, fnOverride, fnRename, fnRenamePlan, functionList, type RenameUse } from "./api";
import { insertableColumn, insertIntoCellEditor, subscribeCellEditor } from "./cellEditor";
import { callOf, filterFunctions } from "./functionExplorer";
import { OVERRIDES_FILE, validFunctionName } from "./fnEditor";
import { PromptDialog } from "./PromptDialog";
import { Confirm } from "./Confirm";
import { FunctionEditor, type EditorControl } from "./FunctionEditor";
import { NewFunctionDialog } from "./NewFunctionDialog";

interface Props {
  project: string | null;
  /** Slid in; the panels stay mounted (and keep their state) while it is out. */
  open: boolean;
  /** A function was saved, added, removed or renamed: what ran with it is stale. */
  onSaved?: () => void;
  /** Shared-folder mode: the text to save (merged with what arrived), "disk" (keep the file as it
   * is on disk), or null (cancelled). */
  reconcile?: (file: string, text: string) => Promise<string | null>;
  /** A rename rewrites the mappings on disk: ask to save the open one first (false = stop)... */
  beforeDiskChange?: () => Promise<boolean>;
  /** ...and read it again afterwards. */
  afterDiskChange?: (message: string) => Promise<void>;
  onClose: () => void;
}

/** A panel beside the grid listing the functions a mapping can call: searchable, with the
 * signature and description of each, and an Insert button for the cell being edited. */
export function FunctionExplorer({ project, open, onSaved, reconcile, beforeDiskChange, afterDiskChange, onClose }: Props) {
  const [all, setAll] = useState<FunctionEntry[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  // the file being edited: the panel widens to the left to hold the editor
  const [editing, setEditing] = useState<{ file: string; focus?: string; nonce: number } | null>(null);
  // what the editor says about its text, to ask before an action replaces it
  const control = useRef<EditorControl>({ dirty: false, save: async () => true });
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameAsk, setRenameAsk] = useState<{ name: string; next: string; use: RenameUse } | null>(null);
  const [pending, setPending] = useState<(() => void) | null>(null);
  const [creating, setCreating] = useState<string[] | null>(null);
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
    if (file !== OVERRIDES_FILE) setLastFile(file);
    setEditing((was) => ({ file, focus, nonce: (was?.nonce ?? 0) + 1 }));
  };
  /** Runs `action`; with unsaved changes in the editor it first asks to save them. */
  const guarded = (action: () => void) => {
    if (editing && control.current.dirty) setPending(() => action);
    else action();
  };
  const rename = async (name: string, next: string) => {
    if (!project) return;
    try {
      if (beforeDiskChange && !(await beforeDiskChange())) return;
      const done = await fnRename(project, name, next);
      await reload();
      setChosen(next);
      setQuery(next);
      if (editing) edit(editing.file, next);
      onSaved?.();
      const calls = done.mappings.reduce((n, m) => n + m.calls, 0);
      await afterDiskChange?.(
        `${name} is now ${next}: ${calls} call${calls === 1 ? "" : "s"} in ${done.mappings.length} mapping${done.mappings.length === 1 ? "" : "s"}, ${done.files.length} function file${done.files.length === 1 ? "" : "s"}`,
      );
    } catch (e) {
      fail(e);
    }
  };
  const override = (name: string) => {
    if (!project) return;
    fnOverride(project, name).then(async ({ file }) => {
      await reload();
      onSaved?.();
      edit(file, name);
    }, fail);
  };
  const create = async (name: string, file: string) => {
    if (!project) return;
    try {
      await fnAdd(project, file, name);
      await reload();
      onSaved?.();
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
            reconcile={reconcile}
            functions={all}
            onChanged={() => {
              void reload();
              onSaved?.();
            }}
            onOpen={(file) => edit(file)}
            onClose={() => setEditing(null)}
          />
        )}
      </div>
      <aside className="explorer" aria-label="Function explorer">
      <div className="explorer-bar">
        <strong>Functions</strong>
        {project && (
          <button onClick={() =>
              fnFiles(project).then(
                (files) => setCreating(files.filter((f) => !f.overrides).map((f) => f.name)),
                fail,
              )
            } title="Add a function to a file of the project">
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
          {project && !current.builtin && !current.replaces_builtin && (
            <button
              onClick={() => guarded(() => setRenaming(current.name))}
              title="Rename it, in its file, the other functions and every mapping that calls it"
            >
              Rename…
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
      {renaming && (
        <PromptDialog
          title={`Rename ${renaming}`}
          confirm="Next"
          fields={[{ key: "name", label: "New name", value: renaming }]}
          validate={({ name }) =>
            name === renaming
              ? "the same name"
              : (validFunctionName(name) ?? (all.some((f) => f.name === name) ? "a function with that name exists" : null))
          }
          onDone={(values) => {
            const old = renaming;
            setRenaming(null);
            if (!values || !project) return;
            fnRenamePlan(project, old).then((use) => setRenameAsk({ name: old, next: values.name, use }), fail);
          }}
        />
      )}
      {renameAsk && (
        <Confirm
          message={`Rename ${renameAsk.name} to ${renameAsk.next}? It changes ${renameAsk.use.files.length} function file(s) (${renameAsk.use.files.map((f) => `fn/${f}.fn`).join(", ") || "none"}) and ${renameAsk.use.mappings.length} mapping(s) (${renameAsk.use.mappings.map((m) => `${m.name}: ${m.calls}`).join(", ") || "none"}). The mappings are saved in the tool's own format.`}
          choices={[
            { id: "rename", label: "Rename", primary: true },
            { id: "cancel", label: "Cancel" },
          ]}
          onChoose={(id) => {
            const ask = renameAsk;
            setRenameAsk(null);
            if (id === "rename") void rename(ask.name, ask.next);
          }}
        />
      )}
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
        <NewFunctionDialog
          files={creating}
          last={lastFile}
          taken={all.map((f) => f.name)}
          onDone={(result) => {
            setCreating(null);
            if (result) guarded(() => void create(result.name, result.file));
          }}
        />
      )}
    </div>
  );
}
