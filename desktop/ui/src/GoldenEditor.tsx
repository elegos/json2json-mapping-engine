import { useEffect, useMemo, useState } from "react";
import { goldenRead, goldenWrite } from "./api";
import { CodeEditor } from "./CodeEditor";
import {
  changedRoles,
  type Files,
  firstProblem,
  formatJson,
  jsonProblem,
  type Role,
  ROLES,
} from "./goldenEdit";

interface Props {
  project: string;
  mapping: string;
  name: string;
  /** Tells the page whether there is something unsaved (to guard leaving it). */
  onDirty: (dirty: boolean) => void;
  /** The files saved: the list of cases shows which a case has. */
  onSaved: () => void;
  onClose: () => void;
}

const errorText = (e: unknown) => String(e instanceof Error ? e.message : e);

/** The three files of a golden case in JSON editors: edit, format, save, remove. */
export function GoldenEditor({ project, mapping, name, onDirty, onSaved, onClose }: Props) {
  const [saved, setSaved] = useState<Files | null>(null);
  const [draft, setDraft] = useState<Files | null>(null);
  const [role, setRole] = useState<Role>("input");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let stale = false;
    goldenRead(project, mapping, name).then(
      (files) => {
        if (stale) return;
        setSaved(files);
        setDraft(files);
      },
      (e) => !stale && setMessage(errorText(e)),
    );
    return () => {
      stale = true;
    };
  }, [project, mapping, name]);

  const changed = useMemo(() => (saved && draft ? changedRoles(saved, draft) : []), [saved, draft]);
  useEffect(() => onDirty(changed.length > 0), [changed.length, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);

  if (!saved || !draft) return <div className="golden-editor muted">{message || "Loading…"}</div>;

  const text = draft[role];
  const problem = text === null ? null : jsonProblem(role, text);
  const about = ROLES.find((r) => r.id === role)?.about ?? "";
  const set = (value: string | null) => setDraft({ ...draft, [role]: value });

  const save = async () => {
    const blocking = firstProblem(saved, draft);
    if (blocking) {
      setRole(blocking.role);
      setMessage(blocking.message);
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      for (const r of changed) await goldenWrite(project, mapping, name, r, draft[r]);
      setSaved(draft);
      onSaved();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="golden-editor" aria-label={`Case ${name}`}>
      <header>
        <strong className="golden-name">{name}</strong>
        <span className="grow" />
        <button className="primary" disabled={busy || changed.length === 0} onClick={() => void save()}>
          Save{changed.length ? " ●" : ""}
        </button>
        <button disabled={busy || changed.length === 0} onClick={() => setDraft(saved)}>
          Revert
        </button>
        <button onClick={onClose} title="Close the editor">
          ✕
        </button>
      </header>
      <div className="tabs">
        {ROLES.map((r) => (
          <button
            key={r.id}
            className={r.id === role ? "tab active" : "tab"}
            onClick={() => {
              setRole(r.id);
              setMessage("");
            }}
          >
            {r.label}
            {changed.includes(r.id) ? " ●" : draft[r.id] === null ? " (none)" : ""}
          </button>
        ))}
      </div>
      <p className="muted golden-about">{about}</p>
      {text === null ? (
        <div className="golden-absent">
          <p>This case has no {ROLES.find((r) => r.id === role)?.label.toLowerCase()}.</p>
          <button onClick={() => set(ROLES.find((r) => r.id === role)?.empty ?? "{}")}>Add one</button>
        </div>
      ) : (
        <>
          <CodeEditor
            key={`${name}|${role}|${saved[role] === null}`}
            className="code-editor multi golden-json"
            singleLine={false}
            language="json"
            value={text}
            onChange={set}
          />
          <div className="golden-tools">
            <span className={problem ? "golden-problem" : "muted"}>{problem ?? "Valid JSON."}</span>
            <span className="grow" />
            <button
              disabled={problem !== null}
              onClick={() => set(formatJson(text) + "\n")}
              title="Indent the JSON"
            >
              Format
            </button>
            {role !== "input" && (
              <button onClick={() => set(null)} title="Remove this file when you save">
                Remove this file
              </button>
            )}
          </div>
        </>
      )}
      {message && <p className="golden-problem">{message}</p>}
    </section>
  );
}
