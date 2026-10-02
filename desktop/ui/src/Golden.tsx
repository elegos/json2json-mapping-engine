import { useEffect, useState } from "react";
import type { GoldenCase, GoldenResult } from "./api";
import { diffLines, falsePositiveNote, maybeFalsePositive, tally, verdict, whyFailed } from "./goldenResult";
import { GoldenEditor } from "./GoldenEditor";

interface Props {
  project: string;
  mapping: string;
  cases: GoldenCase[];
  onImport: () => void;
  onNew: () => void;
  /** Something unsaved in the editor. */
  onDirty: (dirty: boolean) => void;
  /** A file of a case was saved: reload the list. */
  onSaved: () => void;
  /** Runs cases (all without names) and gives their results; null when nothing was run (the user
   * cancelled, or it failed and said so). */
  onRun: (names: string[] | null) => Promise<GoldenResult[] | null>;
  /** Takes the output now as the case's expected result; true when it was done. */
  onRecord: (name: string) => Promise<boolean>;
  /** True to leave the case being edited (nothing unsaved, or the user agreed to lose it). */
  confirmLeave: () => Promise<boolean>;
  onRename: (name: string) => void;
  onDelete: (name: string) => void;
}

/** The golden cases of the open mapping: `tests/golden/<mapping>/<case>.input.json` with an
 * optional expected output and expected rule errors. What is loaded here is what CI runs. */
export function Golden({
  project,
  mapping,
  cases,
  onImport,
  onNew,
  onDirty,
  onSaved,
  onRun,
  onRecord,
  confirmLeave,
  onRename,
  onDelete,
}: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, GoldenResult>>({});
  const [running, setRunning] = useState<string[] | null>(null); // the cases being run
  const [shown, setShown] = useState<string | null>(null); // the result in the detail panel
  const run = async (names: string[] | null) => {
    const wanted = names ?? cases.map((c) => c.name);
    setRunning(wanted);
    try {
      const got = await onRun(names);
      if (got) {
        setResults((old) => ({ ...old, ...Object.fromEntries(got.map((r) => [r.name, r])) }));
        if (names?.length === 1) setShown(names[0]);
      }
    } finally {
      setRunning(null);
    }
  };
  const record = async (name: string) => {
    if (await onRecord(name)) {
      onSaved();
      await run([name]);
    }
  };
  // a result is of the files as they were: editing or renaming a case drops it
  useEffect(() => {
    setResults((old) => Object.fromEntries(Object.entries(old).filter(([n]) => cases.some((c) => c.name === n))));
  }, [cases]);
  // a case renamed or deleted is no longer the one in the editor
  useEffect(() => {
    if (editing && !cases.some((c) => c.name === editing)) setEditing(null);
  }, [cases, editing]);
  const edit = async (name: string) => {
    if (name !== editing && editing !== null && !(await confirmLeave())) return;
    setEditing(name);
  };
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
        <button onClick={onNew}>New case…</button>
        <button
          disabled={running !== null || cases.length === 0}
          title="Run every case on the Python backend (the saved mapping)"
          onClick={() => void run(null)}
        >
          ▶ Execute all
        </button>
        {running && <span className="muted golden-running">Running {running.length === 1 ? running[0] : `${running.length} cases`}…</span>}
        {!running && Object.keys(results).length > 0 && <Summary results={Object.values(results)} />}
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
              <th>Result</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.name} className={c.name === editing ? "current" : undefined}>
                <td className="golden-name">
                  <button className="link" title="Edit this case" onClick={() => void edit(c.name)}>
                    {c.name}
                  </button>
                </td>
                <td>✓</td>
                <td>{c.expected ? "✓" : <span className="golden-none">none</span>}</td>
                <td>{c.errors ? "✓" : <span className="golden-none">none</span>}</td>
                <td>
                  <ResultBadge
                    result={results[c.name]}
                    running={running?.includes(c.name) ?? false}
                    onClick={() => setShown(shown === c.name ? null : c.name)}
                  />
                </td>
                <td className="golden-actions">
                  <button
                    disabled={running !== null}
                    title="Run this case on the Python backend (the saved mapping)"
                    onClick={() => void run([c.name])}
                  >
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
      {shown && results[shown] && (
        <ResultDetail
          result={results[shown]}
          busy={running !== null}
          onRecord={() => void record(shown)}
          onClose={() => setShown(null)}
        />
      )}
      {editing && (
        <GoldenEditor
          project={project}
          mapping={mapping}
          name={editing}
          onDirty={onDirty}
          onSaved={() => {
            setResults((old) => Object.fromEntries(Object.entries(old).filter(([n]) => n !== editing)));
            onSaved();
          }}
          onClose={async () => {
            if (await confirmLeave()) setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function ResultBadge(props: { result?: GoldenResult; running: boolean; onClick: () => void }) {
  if (props.running) return <span className="muted">running…</span>;
  if (!props.result) return <span className="golden-none">not run</span>;
  const v = verdict(props.result);
  return (
    <button className={`result-badge ${v}`} onClick={props.onClick} title="Show the details">
      {v === "pass" ? "PASS" : v === "fail" ? "FAIL" : "output only"}
    </button>
  );
}

function Summary({ results }: { results: GoldenResult[] }) {
  const t = tally(results);
  return (
    <span className="golden-summary">
      <span className="pass">{t.pass} passed</span>
      {t.fail > 0 && <span className="fail">{t.fail} failed</span>}
      {t.shown > 0 && <span className="muted">{t.shown} without expected output</span>}
    </span>
  );
}

/** What a run of one case gave: why it failed, the rule errors, the diff, the output. */
function ResultDetail(props: { result: GoldenResult; busy: boolean; onRecord: () => void; onClose: () => void }) {
  const r = props.result;
  const v = verdict(r);
  return (
    <section className="golden-result" aria-label={`Result of ${r.name}`}>
      <header>
        <strong className="golden-name">{r.name}</strong>
        <span className={`result-badge ${v}`}>{v === "pass" ? "PASS" : v === "fail" ? "FAIL" : "output only"}</span>
        <span className="grow" />
        <button
          disabled={props.busy}
          onClick={props.onRecord}
          title="Make this output, and these rule errors, the expected result of the case"
        >
          Record as expected…
        </button>
        <button onClick={props.onClose} title="Close">
          ✕
        </button>
      </header>
      {v === "fail" && (
        <ul className="golden-why">
          {whyFailed(r).map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {r.errors.length > 0 && (
        <>
          <h4>Rules that reported an error</h4>
          <table className="golden-errors">
            <tbody>
              {r.errors.map((e) => (
                <tr key={e.rule}>
                  <td className="golden-name">{e.rule}</td>
                  <td>
                    {e.cause}
                    {e.expected && <span className="muted"> — expected</span>}
                    {maybeFalsePositive(e, r.target) && <div className="golden-doubt">{falsePositiveNote(r.target)}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {r.diff ? (
        <>
          <h4>Output compared with the expected one</h4>
          <pre className="golden-diff">
            {diffLines(r.diff).map((l, i) => (
              <div key={i} className={l.kind}>
                {l.text}
              </div>
            ))}
          </pre>
        </>
      ) : (
        <>
          <h4>Output</h4>
          <pre className="golden-diff">{JSON.stringify(r.output, null, 2)}</pre>
        </>
      )}
    </section>
  );
}
