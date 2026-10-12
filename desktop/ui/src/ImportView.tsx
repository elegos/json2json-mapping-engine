import { useCallback, useEffect, useRef, useState } from "react";
import {
  type Provider,
  type RunArgs,
  type RunHandle,
  type TestReport,
  chooseDocumentFile,
  importAnswer,
  importApply,
  importList,
  importNote,
  importPlan,
  importProviders,
  importReview,
  importRun,
  importTest,
} from "./api";
import { Confirm } from "./Confirm";
import { ImportQuestions } from "./ImportQuestions";
import { ImportReview } from "./ImportReview";
import {
  type ImportState,
  type ImportSummary,
  type Mode,
  type PlanView,
  type ProfileInfo,
  MODE_LABEL,
  NEXT_STEP,
  applyReport,
} from "./importModel";

interface Props {
  project: string;
  /** Leave the import (always possible; a run that is going on is stopped). */
  onClose: () => void;
  /** The plan was applied: open the mapping it wrote. */
  onApplied: (mapping: string) => void;
}

type Step = "document" | "run" | "questions" | "review" | "apply";

const STEPS: { step: Step; label: string }[] = [
  { step: "document", label: "Document" },
  { step: "run", label: "Run" },
  { step: "questions", label: "Questions" },
  { step: "review", label: "Review" },
  { step: "apply", label: "Apply" },
];

interface RunState {
  args: RunArgs;
  back: Step;
  lines: string[];
  started: number;
  phase: "running" | "failed";
  error?: string;
  details?: string[];
}

const errorText = (e: unknown) => String(e instanceof Error ? e.message : e);
const short = (path: string) => path.replace(/^.*[\\/]/, "");
const PROVIDER_KEY = "importProvider";

const STATE_LABEL: Record<ImportState, string> = {
  needs_answers: "questions to answer",
  answered: "answers to read",
  ready_for_review: "ready for review",
  applied: "applied",
  broken: "unreadable",
};

/** The import of a functional document, full screen: pick the document, let the assistant read it,
 * answer its questions, review the plan, apply it. The files of the import are `import/` in the project. */
export function ImportView({ project, onClose, onApplied }: Props) {
  const [step, setStep] = useState<Step>("document");
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [provider, setProvider] = useState<Provider["id"] | "">("");
  const [imports, setImports] = useState<ImportSummary[]>([]);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [view, setView] = useState<PlanView | null>(null);
  const [run, setRun] = useState<RunState | null>(null);
  const [report, setReport] = useState<TestReport | null>(null);
  const [error, setError] = useState("");
  const [ask, setAsk] = useState<{ message: string; yes: string; then: () => void } | null>(null);
  const handle = useRef<RunHandle | null>(null);
  const cancelled = useRef(false);

  const refresh = useCallback(async () => {
    const list = await importList(project);
    setImports(list.imports);
    setProfiles(list.profiles);
  }, [project]);

  const detect = useCallback(async () => {
    setProviders(null);
    try {
      const found = await importProviders();
      setProviders(found);
      let saved: string | null = null;
      try {
        saved = localStorage.getItem(PROVIDER_KEY);
      } catch {
        /* not persisted */
      }
      setProvider((old) => old || found.find((p) => p.id === saved)?.id || found[0]?.id || "");
    } catch (e) {
      setProviders([]);
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void detect();
    refresh().catch((e) => setError(errorText(e)));
  }, [detect, refresh]);

  const choose = (id: Provider["id"]) => {
    setProvider(id);
    try {
      localStorage.setItem(PROVIDER_KEY, id);
    } catch {
      /* not persisted */
    }
  };

  /** The plan of a mapping, with its checks and cases fresh (they decide what the screens show). */
  const open = useCallback(
    async (mapping: string, to?: Step, recheck = true) => {
      setError("");
      if (recheck) {
        try {
          setReport(await importTest(project, mapping));
        } catch (e) {
          setReport(null);
          setError(`The plan could not be checked: ${errorText(e)}`);
        }
      }
      const v = await importPlan(project, mapping);
      setView(v);
      const next = NEXT_STEP[v.state];
      setStep(to ?? (next === "questions" ? "questions" : "review"));
    },
    [project],
  );

  const startRun = useCallback(
    async (args: RunArgs, back: Step) => {
      setError("");
      cancelled.current = false;
      setRun({ args, back, lines: [], started: Date.now(), phase: "running" });
      setStep("run");
      const fail = (message: string, details?: string[]) =>
        setRun((r) => (r ? { ...r, phase: "failed", error: message, details } : r));
      try {
        const h = await importRun(project, args, (e) => {
          if (e.event === "progress" && e.text) {
            const text = e.text;
            setRun((r) => (r ? { ...r, lines: [...r.lines.slice(-299), text] } : r));
          }
        });
        handle.current = h;
        if (cancelled.current) h.cancel();
        const result = await h.done;
        handle.current = null;
        if (cancelled.current || result.status === "cancelled") {
          await refresh();
          setStep(back === "run" ? "document" : back);
          return;
        }
        if (result.status === "failed" || !result.mapping) {
          fail(result.error ?? "The run failed.", result.details);
          return;
        }
        await refresh();
        await open(result.mapping, result.status === "needs_answers" ? "questions" : "review");
      } catch (e) {
        handle.current = null;
        fail(errorText(e));
      }
    },
    [project, refresh, open],
  );

  const stop = () => {
    cancelled.current = true;
    handle.current?.cancel();
  };

  const running = step === "run" && run?.phase === "running";
  const leave = () => {
    if (running) {
      setAsk({
        message: "A run is going on. Stop it and leave? The plan you had stays as it was.",
        yes: "Stop and leave",
        then: () => {
          stop();
          onClose();
        },
      });
    } else onClose();
  };

  const need = (): Provider["id"] | null => {
    if (!provider) {
      setError("No assistant is installed: install Claude Code or Codex first.");
      return null;
    }
    return provider;
  };

  const mode = (summary: ImportSummary, m: Mode, document?: string) => {
    const p = need();
    if (!p || !summary.document) return;
    void startRun(
      { document: document ?? summary.document, provider: p, mode: m, mapping: summary.mapping, profile: summary.profile },
      "document",
    );
  };

  const continueImport = async (s: ImportSummary) => {
    if (s.state === "answered") mode(s, "resume");
    else await open(s.mapping, undefined, false);
  };

  const canGo = (target: Step) => {
    if (running) return false;
    if (target === "document") return true;
    if (target === "run") return run !== null;
    return view !== null;
  };

  return (
    <div className="import-view" role="dialog" aria-label="Import a document">
      <header className="imp-head">
        <h2>Import a document</h2>
        <span className="muted imp-project" title={project}>
          {short(project)}
        </span>
        <ol className="imp-steps" aria-label="Steps">
          {STEPS.map(({ step: s, label }) => (
            <li key={s}>
              <button
                className={s === step ? "tab active" : "tab"}
                disabled={!canGo(s) && s !== step}
                aria-current={s === step ? "step" : undefined}
                onClick={() => setStep(s)}
              >
                {label}
              </button>
            </li>
          ))}
        </ol>
        {providers && providers.length > 1 && (
          <label className="imp-provider">
            Assistant
            <select value={provider} disabled={running} onChange={(e) => choose(e.target.value as Provider["id"])}>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
        )}
        <button className="imp-close" onClick={leave}>
          {running ? "Stop and close" : "Close"}
        </button>
      </header>
      {error && (
        <p className="wizard-error imp-error" role="alert">
          {error}
        </p>
      )}
      <div className="imp-body">
        {step === "document" && (
          <DocumentStep
            providers={providers}
            provider={provider}
            onProvider={choose}
            onDetect={() => void detect()}
            imports={imports}
            profiles={profiles}
            onContinue={(s) => void continueImport(s)}
            onRedo={(s) =>
              setAsk({
                message: `Redo every rule of ${s.mapping} from the document? Rules you edited are asked about, not overwritten.`,
                yes: MODE_LABEL.rerun_all,
                then: () => mode(s, "rerun_all"),
              })
            }
            onNewVersion={async (s) => {
              const file = await chooseDocumentFile();
              if (file) mode(s, "revalue_version", file);
            }}
            onStart={(document, profile, mapping) => {
              const p = need();
              if (p) void startRun({ document, provider: p, mode: "import", profile, mapping }, "document");
            }}
          />
        )}
        {step === "run" && run && (
          <RunStep
            run={run}
            providers={providers ?? []}
            onStop={stop}
            onBack={() => setStep(run.back === "run" ? "document" : run.back)}
            onRetry={() => void startRun(run.args, run.back)}
          />
        )}
        {step === "questions" && view && (
          <ImportQuestions
            view={view}
            onSubmit={async (answers) => {
              const p = need();
              if (!p) return;
              try {
                await importAnswer(project, view.plan.mapping.id, answers);
              } catch (e) {
                setError(errorText(e));
                return;
              }
              await startRun(
                {
                  document: view.plan.document.file,
                  provider: p,
                  mode: "resume",
                  mapping: view.plan.mapping.id,
                  profile: view.plan.profile?.name,
                },
                "questions",
              );
            }}
            onSkipToReview={() => setStep("review")}
          />
        )}
        {step === "review" && view && (
          <ImportReview
            view={view}
            report={report}
            onReview={async (kind, id, state) => {
              try {
                await importReview(project, view.plan.mapping.id, kind, id, state);
                setView(await importPlan(project, view.plan.mapping.id));
              } catch (e) {
                setError(errorText(e));
              }
            }}
            onAskAgain={async (id, text) => {
              const p = need();
              if (!p) return;
              try {
                await importNote(project, view.plan.mapping.id, id, text);
              } catch (e) {
                setError(errorText(e));
                return;
              }
              await startRun(
                {
                  document: view.plan.document.file,
                  provider: p,
                  mode: "rerun_partial",
                  mapping: view.plan.mapping.id,
                  profile: view.plan.profile?.name,
                  ruleIds: [id],
                },
                "review",
              );
            }}
            onRedoAll={() =>
              setAsk({
                message: "Redo every rule from the document? Rules you edited are asked about, not overwritten.",
                yes: MODE_LABEL.rerun_all,
                then: () => {
                  const p = need();
                  if (p)
                    void startRun(
                      {
                        document: view.plan.document.file,
                        provider: p,
                        mode: "rerun_all",
                        mapping: view.plan.mapping.id,
                        profile: view.plan.profile?.name,
                      },
                      "review",
                    );
                },
              })
            }
            onApply={() => setStep("apply")}
          />
        )}
        {step === "apply" && view && (
          <ApplyStep
            project={project}
            view={view}
            onBack={() => setStep("review")}
            onApplied={(mapping) => {
              void refresh();
              onApplied(mapping);
            }}
          />
        )}
      </div>
      {ask && (
        <Confirm
          message={ask.message}
          choices={[
            { id: "yes", label: ask.yes, primary: true },
            { id: "no", label: "Cancel" },
          ]}
          onChoose={(id) => {
            const then = ask.then;
            setAsk(null);
            if (id === "yes") then();
          }}
        />
      )}
    </div>
  );
}

function DocumentStep(props: {
  providers: Provider[] | null;
  provider: Provider["id"] | "";
  onProvider: (id: Provider["id"]) => void;
  onDetect: () => void;
  imports: ImportSummary[];
  profiles: ProfileInfo[];
  onContinue: (s: ImportSummary) => void;
  onRedo: (s: ImportSummary) => void;
  onNewVersion: (s: ImportSummary) => void;
  onStart: (document: string, profile?: string, mapping?: string) => void;
}) {
  const [document, setDocument] = useState("");
  const [profile, setProfile] = useState("");
  const [mapping, setMapping] = useState("");
  const mappingOk = mapping === "" || /^[A-Za-z0-9_][A-Za-z0-9_-]*$/.test(mapping);
  const found = props.providers ?? [];
  return (
    <div className="imp-document">
      {props.imports.length > 0 && (
        <section aria-label="Imports in this project">
          <h3>In this project</h3>
          <table className="imp-table">
            <thead>
              <tr>
                <th>Mapping</th>
                <th>Document</th>
                <th>State</th>
                <th>Rules</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {props.imports.map((s) => (
                <tr key={s.mapping}>
                  <td>{s.mapping}</td>
                  <td title={s.document}>
                    {s.document ? short(s.document) : "—"}
                    {s.version ? <span className="muted"> v{s.version}</span> : null}
                  </td>
                  <td>
                    <span className={`imp-state ${s.state}`}>{STATE_LABEL[s.state]}</span>
                    {s.error && <div className="lookup-issue error">{s.error}</div>}
                    {(s.stale ?? []).map((w) => (
                      <div key={w} className="lookup-issue warning">
                        the {w} changed since this plan was made
                      </div>
                    ))}
                  </td>
                  <td>
                    {s.rules ?? 0}
                    {s.guesses ? <span className="muted"> · {s.guesses} low or guess</span> : null}
                    {s.open_questions ? <span className="muted"> · {s.open_questions} open</span> : null}
                  </td>
                  <td className="imp-actions">
                    {s.state !== "broken" && (
                      <>
                        <button className="primary" onClick={() => props.onContinue(s)}>
                          {s.state === "applied" ? "View" : s.state === "answered" ? "Continue the run" : "Continue"}
                        </button>
                        <button onClick={() => props.onRedo(s)}>Redo all</button>
                        <button onClick={() => props.onNewVersion(s)}>New version…</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <section aria-label="Import a document">
        <h3>Import a document</h3>
        <p className="imp-help">
          An assistant (Claude Code or Codex, installed on this computer) reads a functional specification —
          spreadsheet, Word, PDF or text — and proposes the rules. You answer what it could not decide,
          review the plan, and only then is anything written into the project.
        </p>
        <label className="prompt-field">
          <span>Document</span>
          <div className="row">
            <input value={document} readOnly placeholder="xlsx, docx, pdf, txt or md" title={document} />
            <button
              onClick={async () => {
                const file = await chooseDocumentFile();
                if (file) setDocument(file);
              }}
            >
              Choose…
            </button>
          </div>
        </label>
        <fieldset className="prompt-field imp-providers">
          <legend>Assistant</legend>
          {props.providers === null && <span className="muted">Looking for assistants…</span>}
          {props.providers !== null && found.length === 0 && (
            <p className="wizard-error">
              No assistant found. Install Claude Code (<code>claude</code>) or Codex (<code>codex</code>) so that it
              is on the PATH, then{" "}
              <button className="link" onClick={props.onDetect}>
                look again
              </button>
              .
            </p>
          )}
          {found.map((p) => (
            <label key={p.id} className="modal-option">
              <input
                type="radio"
                name="provider"
                checked={props.provider === p.id}
                onChange={() => props.onProvider(p.id)}
              />
              {p.title}
              <span className="muted"> {p.version ?? ""}</span>
            </label>
          ))}
        </fieldset>
        <label className="prompt-field">
          <span>Profile (how this kind of document is read)</span>
          <select value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="">Let the assistant propose one</option>
            {props.profiles.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
                {p.description ? ` — ${p.description}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="prompt-field">
          <span>Mapping name (optional)</span>
          <input value={mapping} spellCheck={false} onChange={(e) => setMapping(e.target.value.trim())} />
          <small>
            {mappingOk
              ? "Leave empty to have the assistant list the mappings in the document and ask which one."
              : "Letters, digits, _ and -."}
          </small>
        </label>
        <p className="imp-help">
          Privacy: the text of the document is sent to the assistant you choose, under your account with it. Nothing
          else leaves this computer, and the assistant may write only inside the project's <code>import/</code> folder.
        </p>
        <div className="modal-buttons">
          <button
            className="primary"
            disabled={!document || !props.provider || !mappingOk}
            onClick={() => props.onStart(document, profile || undefined, mapping || undefined)}
          >
            Start the import
          </button>
        </div>
      </section>
    </div>
  );
}

function RunStep(props: {
  run: RunState;
  providers: Provider[];
  onStop: () => void;
  onBack: () => void;
  onRetry: () => void;
}) {
  const { run } = props;
  const [now, setNow] = useState(Date.now());
  const tail = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (run.phase !== "running") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [run.phase]);
  useEffect(() => {
    tail.current?.scrollIntoView({ block: "end" });
  }, [run.lines.length]);
  const seconds = Math.max(0, Math.floor((now - run.started) / 1000));
  const title = props.providers.find((p) => p.id === run.args.provider)?.title ?? run.args.provider;
  return (
    <div className="imp-run">
      <h3>
        {MODE_LABEL[run.args.mode]}: {short(run.args.document)}
      </h3>
      {run.phase === "running" ? (
        <p role="status">
          {title} is working — {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}. This takes minutes for a
          large document.
        </p>
      ) : (
        <div role="alert">
          <p className="wizard-error">The run failed: {run.error}</p>
          {run.details && (
            <ul className="imp-details">
              {run.details.map((d) => (
                <li key={d}>
                  <code>{d}</code>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="imp-log" aria-label="Progress">
        {run.lines.length === 0 && <span className="muted">Waiting for the first words…</span>}
        {run.lines.map((l, i) => (
          <div key={i}>{l}</div>
        ))}
        <div ref={tail} />
      </div>
      <div className="modal-buttons">
        {run.phase === "running" ? (
          <button onClick={props.onStop}>Cancel the run</button>
        ) : (
          <>
            <button onClick={props.onBack}>Back</button>
            <button className="primary" onClick={props.onRetry}>
              Try again
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function ApplyStep(props: {
  project: string;
  view: PlanView;
  onBack: () => void;
  onApplied: (mapping: string) => void;
}) {
  const { project, view } = props;
  const mapping = view.plan.mapping.id;
  const [report, setReport] = useState<TestReport | null>(null);
  const [plan, setPlan] = useState(view);
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [written, setWritten] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const tested = await importTest(project, mapping);
        const fresh = await importPlan(project, mapping);
        if (!live) return;
        setReport(tested);
        setPlan(fresh);
      } catch (e) {
        if (live) setError(errorText(e));
      } finally {
        if (live) setBusy(false);
      }
    })();
    return () => {
      live = false;
    };
  }, [project, mapping]);

  const summary = applyReport(plan.plan, plan.exists);
  const needsForce = plan.exists || (report?.gaps.length ?? 0) > 0;
  const blocked = busy || summary.blockers.length > 0 || report?.ok === false || (needsForce && !force);

  return (
    <div className="imp-apply">
      <h3>Apply to the project</h3>
      {busy && <p role="status">Checking the plan…</p>}
      {written ? (
        <>
          <p role="status">
            Written to <code>{written}</code>. The rules the assistant was not sure of are marked for review in the grid.
          </p>
          <div className="modal-buttons">
            <button className="primary" onClick={() => props.onApplied(mapping)}>
              Open {mapping}
            </button>
          </div>
        </>
      ) : (
        <>
          <ul className="imp-facts">
            <li>
              <strong>{summary.included}</strong> rule(s) will be written to{" "}
              <code>mappings/functional/{mapping}.fn.yaml</code>
              {summary.rejected ? `; ${summary.rejected} rejected stay out` : ""}.
            </li>
            <li>
              {summary.pending} of them are not reviewed yet — they are written all the same, flagged for review when they are
              not high confidence.
            </li>
            {report && (
              <li>
                Checks: {report.ok ? "the working copy passes" : "the working copy does not pass"}; cases: {report.pass} pass,{" "}
                {report.fail} fail, {report.error} error, {report.not_run} not run.
                {report.compile_error ? ` ${report.compile_error}` : ""}
              </li>
            )}
            {report && !report.schemas_found.input && !report.schemas_found.output && (
              <li className="lookup-issue warning">
                No schema was found, so no path was verified. Import the schemas into the project first if you have them.
              </li>
            )}
          </ul>
          {summary.blockers.map((b) => (
            <p key={b} className="wizard-error">
              {b}
            </p>
          ))}
          {report?.ok === false && (
            <p className="wizard-error">
              The working copy does not pass its check: go back and reject or fix the rules that fail (the review lists them).
            </p>
          )}
          {summary.warnings.map((w) => (
            <p key={w} className="lookup-issue warning">
              {w}
            </p>
          ))}
          {report && report.gaps.length > 0 && (
            <details>
              <summary>{report.gaps.length} required output field(s) without a rule</summary>
              <ul>
                {report.gaps.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </details>
          )}
          {needsForce && !busy && (
            <label className="modal-option">
              <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
              {plan.exists
                ? `Replace the existing ${mapping}.fn.yaml`
                : "Write it although required output fields have no rule yet"}
            </label>
          )}
          {error && <p className="wizard-error">{error}</p>}
          <div className="modal-buttons">
            <button onClick={props.onBack}>Back to the review</button>
            <button
              className="primary"
              disabled={blocked}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  const done = await importApply(project, mapping, force);
                  setWritten(done.file);
                } catch (e) {
                  setError(errorText(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Apply
            </button>
          </div>
        </>
      )}
    </div>
  );
}
