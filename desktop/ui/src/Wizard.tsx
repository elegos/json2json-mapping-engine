import { useEffect, useMemo, useState } from "react";
import {
  chooseProject,
  chooseSchemaFile,
  configCheck,
  importSchema,
  listFnFiles,
  mappingCreate,
  projectBackends,
  projectCreate,
  readFn,
  scaffoldRules,
  writeFn,
} from "./api";
import { nameProblem } from "./mappings";
import type { ConfigIssue, ConfigOption, ConfigSchema } from "./projectConfig";
import { WIZARD_TEXTS as T } from "./wizardTexts";

interface Props {
  recent: string[];
  showAtStartup: boolean;
  onShowAtStartup: (value: boolean) => void;
  onOpenDialog: () => void;
  onOpenRecent: (dir: string) => void;
  onForget: (dir: string) => void;
  /** A project was created (and may hold mappings): open it, and its properties if asked. */
  onCreated: (dir: string, properties: boolean) => void;
  onClose: () => void;
  onHelp: () => void;
  /** Import a functional document into `dir` (the wizard closes; the import takes the screen). */
  onImport: (dir: string) => void;
}

type Step = "start" | "project" | "mappings" | "done" | "importProject";

const errorText = (e: unknown) => String(e instanceof Error ? e.message : e);

/** The modal shown at start: recent projects, open, create a project (with its first mappings). */
export function Wizard({
  recent,
  showAtStartup,
  onShowAtStartup,
  onOpenDialog,
  onOpenRecent,
  onForget,
  onCreated,
  onClose,
  onHelp,
  onImport,
}: Props) {
  const [step, setStep] = useState<Step>("start");
  const [dir, setDir] = useState("");
  const [schema, setSchema] = useState<ConfigSchema | null>(null);
  const [target, setTarget] = useState("");
  const [options, setOptions] = useState<Record<string, string | boolean>>({});
  const [made, setMade] = useState(false);
  const [mappings, setMappings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    projectBackends().then(
      (s) => {
        setSchema(s);
        const choices = s.engine.flatMap((sec) => sec.options).find((o) => o.key === "target")?.choices ?? [];
        setTarget((t) => t || choices[0] || "");
      },
      (e) => setError(errorText(e)),
    );
  }, []);

  const backends = useMemo(
    () => schema?.engine.flatMap((s) => s.options).find((o) => o.key === "target")?.choices ?? [],
    [schema],
  );

  // what the backend says about the values typed so far (its own limits and rules)
  const [issues, setIssues] = useState<ConfigIssue[]>([]);
  const targetOptions = schema?.targets[target];
  useEffect(() => {
    if (!target || !targetOptions || step !== "project") return;
    let stale = false;
    const timer = setTimeout(() => {
      const values = { project: { mode: "driven", target }, target: { [target]: optionValues(targetOptions, options) } };
      configCheck(values).then(
        (found) => !stale && setIssues(found),
        () => {},
      );
    }, 150);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [step, target, targetOptions, options]);
  const prefix = `target.${target}.`;
  const problems: Record<string, string> = {};
  for (const i of issues) {
    // "required" is shown by the asterisk, and the button waits for it anyway
    if (i.path.startsWith(prefix) && i.message !== "required") problems[i.path.slice(prefix.length)] = i.message;
  }
  const general = issues.filter((i) => i.path === "");
  const blocked = Object.keys(problems).length > 0 || general.length > 0;

  return (
    <div className="modal-backdrop" onClick={step === "start" ? onClose : undefined}>
      <div
        className="modal wizard"
        role="dialog"
        aria-modal="true"
        aria-label="Start"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && step === "start" && onClose()}
      >
        {step === "start" && (
          <StartPage
            recent={recent}
            showAtStartup={showAtStartup}
            onShowAtStartup={onShowAtStartup}
            onOpenDialog={onOpenDialog}
            onOpenRecent={onOpenRecent}
            onForget={onForget}
            onNew={() => {
              setError("");
              setStep("project");
            }}
            onClose={onClose}
            onHelp={onHelp}
            onImport={() => setStep("importProject")}
          />
        )}
        {step === "importProject" && (
          <ImportProjectPage
            recent={recent}
            onPick={onImport}
            onOpenDialog={async () => {
              const picked = await chooseProject(recent[0], "Project to import into");
              if (picked) onImport(picked);
            }}
            onNew={() => {
              setError("");
              setStep("project");
            }}
            onBack={() => setStep("start")}
          />
        )}
        {step === "project" && (
          <>
            <h3>New project</h3>
            <label className="prompt-field">
              <span>Folder</span>
              <div className="row">
                <input value={dir} spellCheck={false} onChange={(e) => setDir(e.target.value)} />
                <button
                  onClick={async () => {
                    const picked = await chooseProject(dir || recent[0], "Folder of the new project");
                    if (picked) setDir(picked);
                  }}
                >
                  Choose…
                </button>
              </div>
              <small>{T.projectFolder}</small>
            </label>
            <label className="prompt-field">
              <span>Backend</span>
              <select value={target} onChange={(e) => setTarget(e.target.value)}>
                {backends.map((b) => (
                  <option key={b}>{b}</option>
                ))}
              </select>
              <small>{T.backend}</small>
            </label>
            <BackendOptions
              options={schema?.targets[target] ?? []}
              values={options}
              problems={problems}
              onChange={setOptions}
            />
            {general.map((i, k) => (
              <p key={k} className="wizard-error">
                {i.message}
              </p>
            ))}
            {error && <p className="wizard-error">{error}</p>}
            <div className="modal-buttons">
              <button onClick={() => setStep("start")} disabled={busy}>
                Back
              </button>
              <button
                className="primary"
                disabled={busy || blocked || !dir.trim() || !target || missingRequired(schema?.targets[target] ?? [], options)}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    await projectCreate(dir.trim(), target, optionValues(schema?.targets[target] ?? [], options));
                    setMade(true);
                    setStep("mappings");
                  } catch (e) {
                    setError(errorText(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Create project
              </button>
            </div>
          </>
        )}
        {step === "mappings" && (
          <MappingsPage
            dir={dir.trim()}
            mappings={mappings}
            onAdded={(name) => setMappings((m) => [...m, name])}
            onDone={() => setStep("done")}
            onImport={() => onImport(dir.trim())}
            created={made}
          />
        )}
        {step === "done" && (
          <>
            <h3>Project ready</h3>
            <p>{T.projectReady}</p>
            <div className="modal-buttons">
              <button onClick={() => onCreated(dir.trim(), false)}>Not now</button>
              <button autoFocus className="primary" onClick={() => onCreated(dir.trim(), true)}>
                Open the project properties
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StartPage(props: {
  recent: string[];
  showAtStartup: boolean;
  onShowAtStartup: (value: boolean) => void;
  onOpenDialog: () => void;
  onOpenRecent: (dir: string) => void;
  onForget: (dir: string) => void;
  onNew: () => void;
  onClose: () => void;
  onHelp: () => void;
  onImport: () => void;
}) {
  const [missing, setMissing] = useState<ReadonlySet<string>>(new Set());
  useEffect(() => {
    let live = true;
    void Promise.all(
      props.recent.map((d) => listFnFiles(d).then(() => null, () => d)),
    ).then((gone) => live && setMissing(new Set(gone.filter((d): d is string => d !== null))));
    return () => {
      live = false;
    };
  }, [props.recent]);
  return (
    <>
      <h3>JSON to JSON mapping</h3>
      <div className="wizard-recent-title">Recent projects</div>
      <ul className="wizard-recent" aria-label="Recent projects">
        {props.recent.length === 0 && <li className="empty">No project opened yet.</li>}
        {props.recent.map((d) => (
          <li key={d} className={missing.has(d) ? "gone" : undefined} title={d}>
            <button className="link" disabled={missing.has(d)} onClick={() => props.onOpenRecent(d)}>
              {d}
            </button>
            {missing.has(d) && (
              <button className="forget" aria-label={`Remove ${d} from the list`} onClick={() => props.onForget(d)}>
                ✕
              </button>
            )}
          </li>
        ))}
      </ul>
      <small>{T.recent}</small>
      <div className="wizard-actions">
        <button onClick={props.onOpenDialog}>Open project…</button>
        <button className="primary" onClick={props.onNew}>
          New project…
        </button>
        <button onClick={props.onImport} title="Read a functional specification (Excel, Word, PDF, text) and propose the rules">
          Import a document…
        </button>
        <button onClick={props.onHelp}>Help</button>
      </div>
      <div className="modal-buttons wizard-foot">
        <label className="modal-option">
          <input
            type="checkbox"
            checked={props.showAtStartup}
            onChange={(e) => props.onShowAtStartup(e.target.checked)}
          />
          Show this at startup
        </label>
        <button onClick={props.onClose}>Close</button>
      </div>
    </>
  );
}

type Typed = Record<string, string | boolean>;

/** What the form shows for an option: what was typed, else what the backend proposes. */
const shown = (o: ConfigOption, values: Typed): string | boolean | undefined =>
  values[o.key] ?? (o.suggest == null ? undefined : (o.suggest as string | boolean));

function optionValues(options: ConfigOption[], values: Typed) {
  const out: Record<string, unknown> = {};
  for (const o of options) {
    const v = shown(o, values);
    if (v === undefined || v === "" || o.kind === "table") continue;
    out[o.key] = o.kind === "int" ? Number(v) : v;
  }
  return out;
}

function missingRequired(options: ConfigOption[], values: Typed) {
  return options.some(
    (o) => o.required && o.default == null && (shown(o, values) === undefined || shown(o, values) === ""),
  );
}

/** The backend's keys: the ones it needs first, the rest folded away. */
function BackendOptions(props: {
  options: ConfigOption[];
  values: Record<string, string | boolean>;
  /** What the check says about a key, by key. */
  problems: Record<string, string>;
  onChange: (values: Record<string, string | boolean>) => void;
}) {
  const editable = props.options.filter((o) => o.kind !== "table");
  // the keys the backend cannot default come first: those it must be given, and those it proposes
  const needed = editable.filter((o) => (o.required && o.default == null) || o.suggest != null);
  const rest = editable.filter((o) => !needed.includes(o));
  const field = (o: ConfigOption) => (
    <label key={o.key} className="prompt-field">
      <span>
        {o.key}
        {o.required && o.default == null ? " *" : ""}
      </span>
      {o.kind === "bool" ? (
        <input
          type="checkbox"
          checked={(props.values[o.key] ?? o.default) === true}
          onChange={(e) => props.onChange({ ...props.values, [o.key]: e.target.checked })}
        />
      ) : o.kind === "choice" ? (
        <select
          value={String(props.values[o.key] ?? o.default ?? "")}
          onChange={(e) => props.onChange({ ...props.values, [o.key]: e.target.value })}
        >
          {o.choices.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      ) : (
        <input
          value={String(shown(o, props.values) ?? "")}
          placeholder={o.default == null ? "" : String(o.default)}
          inputMode={o.kind === "int" ? "numeric" : undefined}
          spellCheck={false}
          onChange={(e) => props.onChange({ ...props.values, [o.key]: e.target.value })}
        />
      )}
      {props.problems[o.key] ? (
        <small className="wizard-error">{props.problems[o.key]}</small>
      ) : (
        <small>{o.help}</small>
      )}
    </label>
  );
  return (
    <>
      {needed.map(field)}
      {rest.length > 0 && (
        <details className="wizard-more">
          <summary>More options</summary>
          {rest.map(field)}
        </details>
      )}
    </>
  );
}

function MappingsPage(props: {
  dir: string;
  mappings: string[];
  created: boolean;
  onAdded: (name: string) => void;
  onDone: () => void;
  onImport: () => void;
}) {
  const [name, setName] = useState("");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [prefill, setPrefill] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const problem = nameProblem(name.trim(), props.mappings);

  const add = async () => {
    const stem = name.trim();
    setBusy(true);
    setError("");
    try {
      const { file } = await mappingCreate(props.dir, stem);
      if (input) await importSchema(props.dir, stem, "input", input);
      if (output) {
        await importSchema(props.dir, stem, "output", output);
        if (prefill) {
          const tree = await readFn(props.dir, file);
          const made = await scaffoldRules(tree, props.dir, stem, true);
          if (made.tree) await writeFn(props.dir, file, made.tree);
        }
      }
      props.onAdded(stem);
      setName("");
      setInput("");
      setOutput("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const picker = (kind: "input" | "output", value: string, set: (v: string) => void, hint: string) => (
    <label className="prompt-field">
      <span>{kind === "input" ? "Input JSON Schema" : "Output JSON Schema"} (optional)</span>
      <div className="row">
        <input value={value} readOnly placeholder="none" />
        <button
          onClick={async () => {
            const picked = await chooseSchemaFile(kind, props.dir);
            if (picked) set(picked);
          }}
        >
          Choose…
        </button>
        {value && <button onClick={() => set("")}>Clear</button>}
      </div>
      <small>{hint}</small>
    </label>
  );

  return (
    <>
      <h3>Project created — add mappings</h3>
      {props.mappings.length > 0 && (
        <p className="wizard-added">Added: {props.mappings.join(", ")}</p>
      )}
      <label className="prompt-field">
        <span>Mapping name</span>
        <input autoFocus value={name} spellCheck={false} onChange={(e) => setName(e.target.value)} />
        <small>{name && problem ? problem : T.mappingName}</small>
      </label>
      {picker("input", input, setInput, T.inputSchema)}
      {picker("output", output, setOutput, T.outputSchema)}
      {output && (
        <label className="modal-option">
          <input type="checkbox" checked={prefill} onChange={(e) => setPrefill(e.target.checked)} />
          Pre-fill the rules from the output schema
          <small className="wizard-inline">{T.prefill}</small>
        </label>
      )}
      {error && <p className="wizard-error">{error}</p>}
      <div className="modal-buttons">
        <button disabled={busy || problem !== null} onClick={() => void add()}>
          {props.mappings.length ? "Add another mapping" : "Add mapping"}
        </button>
        <button disabled={busy} onClick={props.onImport} title="Read a functional specification and propose the rules">
          Import a document…
        </button>
        <button className="primary" disabled={busy} onClick={props.onDone}>
          {props.mappings.length ? "Done — open the project" : "Skip — open the project"}
        </button>
      </div>
    </>
  );
}

/** Which project the document goes into: one opened before, one chosen, or a new one. */
function ImportProjectPage(props: {
  recent: string[];
  onPick: (dir: string) => void;
  onOpenDialog: () => void;
  onNew: () => void;
  onBack: () => void;
}) {
  const [missing, setMissing] = useState<ReadonlySet<string>>(new Set());
  useEffect(() => {
    let live = true;
    void Promise.all(props.recent.map((d) => listFnFiles(d).then(() => null, () => d))).then(
      (gone) => live && setMissing(new Set(gone.filter((d): d is string => d !== null))),
    );
    return () => {
      live = false;
    };
  }, [props.recent]);
  return (
    <>
      <h3>Import a document — which project?</h3>
      <ul className="wizard-recent" aria-label="Projects">
        {props.recent.length === 0 && <li className="empty">No project opened yet.</li>}
        {props.recent.map((d) => (
          <li key={d} className={missing.has(d) ? "gone" : undefined} title={d}>
            <button className="link" disabled={missing.has(d)} onClick={() => props.onPick(d)}>
              {d}
            </button>
          </li>
        ))}
      </ul>
      <div className="wizard-actions">
        <button onClick={props.onOpenDialog}>Other project…</button>
        <button onClick={props.onNew}>New project…</button>
      </div>
      <div className="modal-buttons">
        <button onClick={props.onBack}>Back</button>
      </div>
    </>
  );
}
