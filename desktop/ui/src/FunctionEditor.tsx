import { EditorView } from "@codemirror/view";
import { type MutableRefObject, useEffect, useMemo, useRef, useState } from "react";
import {
  type CompletionItem,
  type FnFile,
  type FnIssue,
  type FunctionEntry,
  fnCall,
  fnCheck,
  fnCreate,
  fnDelete,
  fnFiles,
  fnRead,
  fnWrite,
  projectBackends,
} from "./api";
import { CodeEditor, type Completer } from "./CodeEditor";
import { Confirm } from "./Confirm";
import { FUNCTION_SCOPE, pyBuiltinItems, scopeItems } from "./fnNames";
import { argsTemplate, functionNames, newFileProblem, parseArgs } from "./fnEditor";
import { PromptDialog } from "./PromptDialog";

interface Props {
  project: string;
  /** The file to edit (name without `.fn`). */
  file: string;
  /** Changes with each request to open a file: the same file is read again from disk. */
  nonce: number;
  /** What the editor tells its parent: unsaved changes, and a way to save them. */
  control: MutableRefObject<EditorControl>;
  /** The function to try first, when the editor is opened on one. */
  focus?: string;
  /** The registry's functions, for the completion. */
  functions: FunctionEntry[];
  /** A file was saved, created or deleted: the explorer's list is stale. */
  onChanged: () => void;
  onOpen: (file: string) => void;
  onClose: () => void;
}

export interface EditorControl {
  dirty: boolean;
  /** Saves the text; false when the file was refused. */
  save: () => Promise<boolean>;
}

type Asking = null | "new-file" | "delete" | { switchTo: string } | "close";

/**
 * The editor of a project's `fn/*.fn` file, in the explorer's wider panel: the text with Python
 * highlighting and the function names to complete, the issues the registry and the backends
 * find (as the text is typed), and a test call on the Python backend with the text as it is.
 */
export function FunctionEditor({ project, file, nonce, control, focus, functions, onChanged, onOpen, onClose }: Props) {
  const [files, setFiles] = useState<FnFile[]>([]);
  const [saved, setSaved] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [issues, setIssues] = useState<FnIssue[]>([]);
  const [error, setError] = useState("");
  const [asking, setAsking] = useState<Asking>(null);
  const [names, setNames] = useState(false);
  const dirty = saved !== null && text !== saved;

  const loadFiles = () => fnFiles(project).then(setFiles, (e) => setError(String(e.message ?? e)));
  useEffect(() => {
    void loadFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, file]);

  const view = useRef<EditorView | null>(null);
  const cursorAt = useRef<string | undefined>(undefined);
  useEffect(() => {
    let stale = false;
    cursorAt.current = focus;
    // the same file again (a function was added to it): keep the editor, change the text
    setSaved(null);
    fnRead(project, file).then(
      (body) => {
        if (stale) return;
        setSaved(body);
        setText(body);
        setError("");
      },
      (e) => !stale && setError(String(e.message ?? e)),
    );
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, file, nonce]);

  // the cursor goes to the function the file was opened for
  useEffect(() => {
    const editor = view.current;
    if (saved === null || !cursorAt.current || !editor) return;
    const at = new RegExp(`^def\\s+${cursorAt.current}\\b`, "m").exec(saved)?.index;
    cursorAt.current = undefined;
    if (at === undefined) return;
    editor.dispatch({ selection: { anchor: at }, effects: EditorView.scrollIntoView(at, { y: "start", yMargin: 20 }) });
    editor.focus();
  }, [saved]);

  // the issues follow the text, a moment after the last key
  useEffect(() => {
    if (saved === null) return;
    let stale = false;
    const timer = setTimeout(() => {
      fnCheck(project, file, text).then(
        (found) => !stale && setIssues(found),
        () => undefined,
      );
    }, 250);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [project, file, text, saved]);

  // the backends an @override can name
  const [backends, setBackends] = useState<string[]>(["python"]);
  useEffect(() => {
    projectBackends().then(
      (schema) => setBackends(["python", ...Object.keys(schema.targets).filter((t) => t !== "python")]),
      () => undefined,
    );
  }, []);

  const completer: Completer = useMemo(
    () => async (body, cursor) => {
      const before = body.slice(0, cursor);
      // after `_py.`: Python's own built-ins
      const py = /\b_py\.(\w*)$/.exec(before);
      if (py) return { from: cursor - py[1].length, items: pyBuiltinItems(py[1]) };
      const word = /@?[A-Za-z_]\w*$|@$/.exec(before)?.[0] ?? "";
      if (word.startsWith("@")) {
        const items: CompletionItem[] = backends
          .map((b) => ({
            label: `@override(${b}="…")`,
            insert: `@override(${b}="")`,
            kind: "keyword" as const,
            detail: b === "python" ? "a Python expression" : "a template, parameters as {name}",
            doc:
              b === "python"
                ? 'What the Python backend runs instead of the body, with the parameters as {name}: @override(python="{s}.upper()")'
                : `The code ${b} gets for a call, with the parameters as {name}`,
            origin: "decorator",
          }))
          .filter((i) => i.insert.startsWith(word));
        return { from: cursor - word.length, items };
      }
      const items: CompletionItem[] = [...scopeItems(word)];
      items.push(...functions
        .filter((f) => f.name.startsWith(word))
        .map((f) => ({
          label: f.signature,
          insert: f.name,
          kind: "function" as const,
          detail: f.returns,
          doc: f.doc,
          origin: f.origin,
        })));
      return { from: cursor - word.length, items };
    },
    [functions, backends],
  );

  const goToLine = (line: number) => {
    const editor = view.current;
    if (!editor) return;
    const at = editor.state.doc.line(Math.min(Math.max(line, 1), editor.state.doc.lines)).from;
    editor.dispatch({ selection: { anchor: at }, effects: EditorView.scrollIntoView(at, { y: "center" }) });
    editor.focus();
  };

  const save = async () => {
    try {
      await fnWrite(project, file, text);
      setSaved(text);
      setError("");
      onChanged();
      void loadFiles();
      return true;
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      return false;
    }
  };
  control.current = { dirty, save };

  const current = files.find((f) => f.name === file);
  const guarded = (next: Asking, go: () => void) => (dirty ? setAsking(next) : go());
  const blocking = issues.some((i) => i.severity === "error");

  return (
    <section
      className="fn-editor"
      aria-label="Project function editor"
      onKeyDown={(e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "s") {
          e.preventDefault();
          if (dirty) void save();
        }
      }}
    >
      <div className="fn-bar">
        <select
          aria-label="Function file"
          value={file}
          onChange={(e) => {
            const next = e.target.value;
            if (next === "") guarded("new-file", () => setAsking("new-file"));
            else guarded({ switchTo: next }, () => onOpen(next));
          }}
        >
          {files.map((f) => (
            <option key={f.name} value={f.name}>
              fn/{f.name}.fn
              {f.overrides ? " (built-in overrides)" : ""}
            </option>
          ))}
          {!current && <option value={file}>fn/{file}.fn</option>}
          <option value="">New file…</option>
        </select>
        <button onClick={() => setAsking("delete")} title="Delete this file from the project">
          Delete file
        </button>
        <button onClick={() => setNames((on) => !on)} aria-pressed={names} title="The names a function can use">
          Names
        </button>
        <span className="grow" />
        <button className="primary" disabled={!dirty} onClick={() => void save()} title="Ctrl+S">
          Save
        </button>
        <button onClick={() => guarded("close", onClose)} aria-label="Close the editor" title="Close the editor">
          ✕
        </button>
      </div>
      {current?.overrides && (
        <p className="fn-warning">
          Built-in functions: changing them might break the mappings that call them! Each function
          here replaces the built-in of the same name; delete it (or the file) to get the built-in
          back.
        </p>
      )}
      {names && (
        <dl className="fn-names">
          <div>
            <dt>parameters</dt>
            <dd>the ones in the signature, by their names.</dd>
          </div>
          <div>
            <dt>J2JME functions</dt>
            <dd>every function of the list on the right, built-in or the project's.</dd>
          </div>
          {FUNCTION_SCOPE.map((n) => (
            <div key={n.name}>
              <dt>{n.name}</dt>
              <dd>{n.about}</dd>
            </div>
          ))}
        </dl>
      )}
      {error && <p className="wizard-error">{error}</p>}
      {saved !== null && (
        <CodeEditor
          key={file}
          viewRef={view}
          className="code-editor multi fn-text"
          singleLine={false}
          language="python"
          completer={completer}
          value={text}
          onChange={setText}
        />
      )}
      <ul className="fn-issues" aria-label="Issues">
        {issues.length === 0 && saved !== null && <li className="ok">No issues.</li>}
        {issues.map((i, n) => (
          <li key={n} className={i.severity}>
            <button onClick={() => goToLine(i.line)} title="Go to the line">
              line {i.line}
              {i.function ? ` · ${i.function}` : ""}: {i.message}
            </button>
          </li>
        ))}
      </ul>
      {blocking && <p className="explorer-about">An error here makes a build or a golden run fail.</p>}
      <TestCall project={project} text={text} focus={focus} />
      {asking === "new-file" && (
        <PromptDialog
          title="New function file"
          confirm="Create"
          fields={[{ key: "name", label: "File name", value: "", hint: "fn/<name>.fn" }]}
          validate={({ name }) =>
            newFileProblem(name, files.map((f) => f.name))
          }
          onDone={(values) => {
            setAsking(null);
            if (!values) return;
            fnCreate(project, values.name).then(
              () => {
                onChanged();
                onOpen(values.name);
              },
              (e) => setError(String(e.message ?? e)),
            );
          }}
        />
      )}
      {asking === "delete" && (
        <Confirm
          message={`Delete fn/${file}.fn${current?.functions.length ? ` and ${current.functions.join(", ")}` : ""}? Mappings that call them stop building.`}
          choices={[
            { id: "delete", label: "Delete file", primary: true },
            { id: "cancel", label: "Cancel" },
          ]}
          onChoose={(id) => {
            setAsking(null);
            if (id !== "delete") return;
            fnDelete(project, file).then(
              async () => {
                onChanged();
                const rest = (await fnFiles(project)).filter((f) => f.name !== file);
                if (rest.length) onOpen(rest[0].name);
                else onClose();
              },
              (e) => setError(String(e.message ?? e)),
            );
          }}
        />
      )}
      {asking !== null && typeof asking === "object" && (
        <Confirm
          message={`fn/${file}.fn has changes that are not saved.`}
          choices={[
            { id: "save", label: "Save", primary: true },
            { id: "discard", label: "Discard" },
            { id: "cancel", label: "Cancel" },
          ]}
          onChoose={(id) => {
            const next = asking;
            setAsking(null);
            if (id === "cancel") return;
            const go = () => onOpen((next as { switchTo: string }).switchTo);
            if (id === "save") void save().then((ok) => ok && go());
            else go();
          }}
        />
      )}
      {asking === "close" && (
        <Confirm
          message={`fn/${file}.fn has changes that are not saved.`}
          choices={[
            { id: "save", label: "Save", primary: true },
            { id: "discard", label: "Discard" },
            { id: "cancel", label: "Cancel" },
          ]}
          onChoose={(id) => {
            setAsking(null);
            if (id === "cancel") return;
            if (id === "save") void save().then((ok) => ok && onClose());
            else onClose();
          }}
        />
      )}
    </section>
  );
}

/** A call of one of the file's functions on the Python backend, with the text as it is. */
function TestCall({ project, text, focus }: { project: string; text: string; focus?: string }) {
  const names = useMemo(() => functionNames(text), [text]);
  const [name, setName] = useState(focus ?? "");
  const [args, setArgs] = useState("[]");
  const [outcome, setOutcome] = useState<{ ok: boolean; text: string } | null>(null);
  const touched = useRef(false);
  const chosen = names.includes(name) ? name : (names[0] ?? "");

  // the arguments follow the function chosen, until the developer types their own
  useEffect(() => {
    if (!touched.current) setArgs(argsTemplate(text, chosen));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosen]);

  const run = async () => {
    const parsed = parseArgs(args);
    if ("error" in parsed) return setOutcome({ ok: false, text: parsed.error });
    try {
      const answer = await fnCall(project, chosen, parsed.args, text);
      setOutcome(
        answer.error !== undefined
          ? { ok: false, text: answer.error }
          : { ok: true, text: JSON.stringify(answer.result ?? null, null, 2) },
      );
    } catch (e) {
      setOutcome({ ok: false, text: String(e instanceof Error ? e.message : e) });
    }
  };

  if (names.length === 0) return null;
  return (
    <div className="fn-call">
      <strong>Test call</strong>
      <span className="muted"> (Python, the text as it is)</span>
      <div className="fn-call-row">
        <select
          aria-label="Function to call"
          value={chosen}
          onChange={(e) => {
            touched.current = false;
            setName(e.target.value);
            setArgs(argsTemplate(text, e.target.value));
          }}
        >
          {names.map((n) => (
            <option key={n}>{n}</option>
          ))}
        </select>
        <input
          aria-label="Arguments"
          value={args}
          spellCheck={false}
          onChange={(e) => {
            touched.current = true;
            setArgs(e.target.value);
          }}
          onKeyDown={(e) => e.key === "Enter" && void run()}
        />
        <button onClick={() => void run()}>Run</button>
      </div>
      {outcome && <pre className={outcome.ok ? "fn-result" : "fn-result failed"}>{outcome.text}</pre>}
    </div>
  );
}
