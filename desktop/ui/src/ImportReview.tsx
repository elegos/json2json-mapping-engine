import { useMemo, useState } from "react";
import type { TestReport } from "./api";
import {
  type Confidence,
  type Discrepancy,
  type PlanRule,
  type PlanValidation,
  type PlanView,
  FLAG_LABEL,
  countByLevel,
  locationText,
  needsAttention,
  ruleTree,
  visibleRules,
} from "./importModel";

type State = "pending" | "accepted" | "rejected";

interface Props {
  view: PlanView;
  /** The last check-and-run of the plan (null when it could not be done). */
  report: TestReport | null;
  onReview: (kind: "rule" | "validation", id: string, state: State) => Promise<void>;
  /** The user's remark on a rule: saved, and the rule is read again. */
  onAskAgain: (id: string, note: string) => Promise<void>;
  onRedoAll: () => void;
  onApply: () => void;
}

type Tab = "rules" | "validations" | "lookups" | "tests" | "discrepancies" | "coverage" | "setup";

/** The plan of one import: a summary, then rules (list and detail), checks, lookups, cases,
 * discrepancies, coverage, and the schemas and profile it was read with. */
export function ImportReview(props: Props) {
  const { view, report } = props;
  const plan = view.plan;
  const [tab, setTab] = useState<Tab>("rules");
  const levels = countByLevel(plan.rules);
  const open = plan.questions.filter((q) => q.topic !== "user_note" && (q.status ?? "open") === "open").length;
  const errors = plan.discrepancies.filter((d) => d.severity === "error").length;
  const warnings = plan.discrepancies.filter((d) => d.severity === "warning").length;
  const cov = plan.coverage;
  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "rules", label: "Rules", count: plan.rules.length },
    { id: "validations", label: "Validations", count: plan.validations?.length ?? 0 },
    { id: "lookups", label: "Lookups", count: plan.lookups?.length ?? 0 },
    { id: "tests", label: "Cases", count: plan.tests?.length ?? 0 },
    { id: "discrepancies", label: "Discrepancies", count: plan.discrepancies.length },
    { id: "coverage", label: "Coverage" },
    { id: "setup", label: "Schemas & profile" },
  ];
  return (
    <div className="imp-review">
      {view.stale.length > 0 && (
        <p className="lookup-issue warning" role="status">
          The {view.stale.join(" and ")} changed since this plan was made: redo the rules, or read the new version of the
          document, before relying on it.
        </p>
      )}
      {view.problems.length > 0 && (
        <details className="lookup-issue error">
          <summary>The plan does not follow the schema ({view.problems.length} problem(s))</summary>
          <ul>
            {view.problems.map((p) => (
              <li key={p}>
                <code>{p}</code>
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="imp-summary" aria-label="Summary">
        <div>
          <strong>{plan.mapping.id}</strong>
          <span className="muted"> from {plan.document.file.replace(/^.*[\\/]/, "")} v{plan.document.version.resolved}</span>
        </div>
        <div className="imp-levels" aria-label="Confidence">
          {(["high", "medium", "low", "guess"] as const).map((l) => (
            <span key={l} className={`imp-chip level-${l}`}>
              {levels[l]} {l}
            </span>
          ))}
        </div>
        <div>
          {open > 0 ? <span className="imp-chip flag">{open} open question(s)</span> : <span className="muted">no open question</span>}{" "}
          <span className={errors ? "imp-chip level-guess" : "muted"}>{errors} error(s)</span>{" "}
          <span className={warnings ? "imp-chip level-low" : "muted"}>{warnings} warning(s)</span>
        </div>
        {cov?.units_total !== undefined && (
          <div title="units of the document">
            Coverage: {cov.imported ?? 0} imported, {cov.imported_with_doubt ?? 0} with doubt,{" "}
            {cov.not_imported?.length ?? 0} not imported, of {cov.units_total}
          </div>
        )}
        {report && (
          <div>
            Cases: {report.pass} pass, <span className={report.fail + report.error ? "imp-bad" : ""}>{report.fail + report.error} fail</span>,{" "}
            {report.not_run} not run
          </div>
        )}
        <div className="imp-summary-actions">
          <button onClick={props.onRedoAll}>Redo all</button>
          <button className="primary" onClick={props.onApply}>
            Apply…
          </button>
        </div>
      </div>
      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "tab active" : "tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {t.count !== undefined ? ` (${t.count})` : ""}
          </button>
        ))}
      </div>
      <div className="imp-pane">
        {tab === "rules" && <RulesPane {...props} />}
        {tab === "validations" && <ValidationsPane {...props} />}
        {tab === "lookups" && <LookupsPane view={view} />}
        {tab === "tests" && <CasesPane view={view} />}
        {tab === "discrepancies" && <DiscrepanciesPane view={view} onOpen={() => setTab("rules")} />}
        {tab === "coverage" && <CoveragePane view={view} />}
        {tab === "setup" && <SetupPane view={view} />}
      </div>
    </div>
  );
}

export function Chip({ confidence }: { confidence?: Confidence }) {
  const level = confidence?.level ?? "high";
  return <span className={`imp-chip level-${level}`}>{level}</span>;
}

function Flags({ confidence }: { confidence?: Confidence }) {
  return (
    <>
      {(confidence?.flags ?? []).map((f) => (
        <span key={f} className="imp-chip flag">
          {FLAG_LABEL[f] ?? f}
        </span>
      ))}
    </>
  );
}

const STATE_TEXT: Record<string, string> = {
  pending: "",
  accepted: "accepted",
  edited: "edited",
  rejected: "rejected",
  applied: "applied",
};

function RulesPane({ view, onReview, onAskAgain }: Props) {
  const [onlyAttention, setOnlyAttention] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const nodes = useMemo(() => ruleTree(view.plan.rules), [view.plan.rules]);
  const shown = visibleRules(nodes, onlyAttention);
  const rule = view.plan.rules.find((r) => r.id === selected) ?? shown[0]?.rule ?? null;
  const attention = nodes.filter((n) => needsAttention(n.rule)).length;
  return (
    <div className="imp-split">
      <div className="imp-list" aria-label="Rules">
        <label className="modal-option imp-filter">
          <input type="checkbox" checked={onlyAttention} onChange={(e) => setOnlyAttention(e.target.checked)} />
          Only what needs a look ({attention} of {nodes.length})
        </label>
        <ul>
          {shown.map(({ rule: r, depth }) => (
            <li key={r.id}>
              <button
                className={r.id === rule?.id ? "imp-row active" : "imp-row"}
                style={{ paddingLeft: 8 + depth * 14 }}
                onClick={() => setSelected(r.id)}
              >
                <span className="imp-target">{r.target.path}</span>
                <Chip confidence={r.confidence} />
                {STATE_TEXT[r.review.state] && <span className={`imp-state ${r.review.state}`}>{STATE_TEXT[r.review.state]}</span>}
                {r.proposal?.check?.ok === false && <span className="imp-chip level-guess">check fails</span>}
              </button>
            </li>
          ))}
          {shown.length === 0 && <li className="muted imp-empty">Nothing needs a look.</li>}
        </ul>
      </div>
      <div className="imp-detail">
        {rule ? (
          <RuleDetail key={rule.id} rule={rule} view={view} onReview={onReview} onAskAgain={onAskAgain} />
        ) : (
          <p className="muted">Select a rule.</p>
        )}
      </div>
    </div>
  );
}

function Evidence({ item }: { item: PlanRule | PlanValidation }) {
  const e = item.evidence;
  return (
    <section>
      <h4>In the document</h4>
      <div className="muted">{e.locations.map(locationText).join(" · ")}</div>
      <pre className="imp-evidence-text">{e.text}</pre>
      {(e.inherited_context ?? []).map((c, i) => (
        <div key={i} className="imp-context">
          <span className="imp-chip">{c.kind.replace("_", " ")}</span> {c.text}
          {c.location && <span className="muted"> — {locationText(c.location)}</span>}
        </div>
      ))}
      {(e.review_thread ?? []).map((t, i) => (
        <blockquote key={i} className="imp-evidence">
          {t.text}
          <cite>
            {" "}
            — {[t.kind, t.author, t.date].filter(Boolean).join(", ") || "comment in the document"}
          </cite>
        </blockquote>
      ))}
      {(e.markers ?? []).map((m, i) => (
        <div key={i} className="muted">
          Formatting <code>{m.marker}</code>: {m.meaning ?? "meaning unknown"} ({m.meaning_origin ?? "unknown"})
        </div>
      ))}
    </section>
  );
}

/** A rule's `source:` as a line: a path, a constant, or the text as it is. */
function sourceText(source: unknown): string {
  if (typeof source === "string") return source;
  const s = source as { path?: string; constant?: unknown } | null;
  if (s?.path !== undefined) return s.path;
  if (s && "constant" in s) return `constant ${JSON.stringify(s.constant)}`;
  return JSON.stringify(source);
}

function ReviewButtons(props: { state: string; onSet: (s: State) => void }) {
  const locked = props.state === "applied";
  return (
    <div className="imp-review-buttons">
      <button disabled={locked || props.state === "accepted"} onClick={() => props.onSet("accepted")}>
        Accept
      </button>
      <button disabled={locked || props.state === "rejected"} onClick={() => props.onSet("rejected")}>
        Reject
      </button>
      {(props.state === "accepted" || props.state === "rejected") && !locked && (
        <button className="link" onClick={() => props.onSet("pending")}>
          Undo
        </button>
      )}
    </div>
  );
}

function RuleDetail(props: {
  rule: PlanRule;
  view: PlanView;
  onReview: Props["onReview"];
  onAskAgain: Props["onAskAgain"];
}) {
  const { rule: r, view } = props;
  const [note, setNote] = useState(r.review.note ?? "");
  const [busy, setBusy] = useState(false);
  const fn = r.proposal?.fn_rule;
  const expression = (fn?.transform as { expression?: string } | undefined)?.expression;
  const related = view.plan.discrepancies.filter((d) => d.rule_ids?.includes(r.id));
  const tests = (view.plan.tests ?? []).filter((t) => t.rule_ids?.includes(r.id));
  const questions = view.plan.questions.filter((q) => q.rule_ids?.includes(r.id) && q.topic !== "user_note");
  return (
    <article className="imp-rule">
      <header>
        <h3>{r.target.path}</h3>
        <div>
          <Chip confidence={r.confidence} /> <Flags confidence={r.confidence} />{" "}
          <span className="muted">{r.intent}</span>
        </div>
        <ReviewButtons state={r.review.state} onSet={(s) => void props.onReview("rule", r.id, s)} />
      </header>
      {(r.confidence.reasons ?? []).length > 0 && (
        <ul className="imp-reasons">
          {r.confidence.reasons?.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      )}
      <Evidence item={r} />
      <section>
        <h4>What the assistant understood</h4>
        <p>{r.interpretation}</p>
        {(r.assumptions ?? []).length > 0 && (
          <table className="imp-assumptions">
            <thead>
              <tr>
                <th>Assumed</th>
                <th>Because</th>
              </tr>
            </thead>
            <tbody>
              {r.assumptions?.map((a, i) => (
                <tr key={i}>
                  <td>
                    <span className="muted">{a.topic}: </span>
                    {a.assumed}
                  </td>
                  <td className={a.basis === "guess" ? "imp-bad" : undefined}>{a.basis.replace(/_/g, " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {questions.map((q) => (
          <div key={q.id} className="muted">
            Question: {q.text} — {q.status === "answered" ? `answered: ${q.answer}` : (q.status ?? "open").replace(/_/g, " ")}
          </div>
        ))}
      </section>
      <section>
        <h4>The rule it proposes</h4>
        {fn ? (
          <>
            <dl className="imp-fn">
              <dt>{String(fn.kind)}</dt>
              <dd>
                {fn.field ? <code>{String(fn.field)}</code> : null}
                {fn.output ? <code>{String(fn.output)}</code> : null}
                {fn.source ? (
                  <>
                    {" "}
                    ← <code>{sourceText(fn.source)}</code>
                  </>
                ) : null}
              </dd>
            </dl>
            {expression && <pre className="imp-code">{expression}</pre>}
            {fn.guard ? <div className="muted">only if: <code>{String(fn.guard)}</code></div> : null}
            <details>
              <summary>The rule as written in the file</summary>
              <pre className="imp-code">{JSON.stringify(fn, null, 2)}</pre>
            </details>
          </>
        ) : (
          <p className="muted">No rule yet — the assistant needs an answer or a function the catalogue lacks.</p>
        )}
        {(r.proposal?.functions_missing ?? []).map((m, i) => (
          <div key={i} className="lookup-issue warning">
            Missing function: {m.needed}
            {m.suggestion ? ` (${m.suggestion})` : ""}
          </div>
        ))}
        {r.proposal?.check?.ran && (
          <div className={r.proposal.check.ok ? "muted" : "lookup-issue error"}>
            {r.proposal.check.ok ? "Passes the check." : "Does not pass the check:"}
            {(r.proposal.check.errors ?? []).map((e) => (
              <div key={e}>{e}</div>
            ))}
          </div>
        )}
        {r.back_translation && (
          <p className="muted">
            Read back from the rule: <em>{r.back_translation}</em>
          </p>
        )}
      </section>
      {(related.length > 0 || tests.length > 0) && (
        <section>
          <h4>Related</h4>
          {related.map((d, i) => (
            <DiscrepancyLine key={i} d={d} />
          ))}
          {tests.map((t) => (
            <div key={t.id} className={t.result === "pass" ? "muted" : t.result === "fail" || t.result === "error" ? "imp-bad" : "muted"}>
              Case {t.id}: {t.result ?? "not run"} {t.detail ? `— ${t.detail}` : ""}
            </div>
          ))}
        </section>
      )}
      <section>
        <h4>Not right?</h4>
        <textarea
          rows={2}
          value={note}
          placeholder="Tell the assistant what it got wrong or what the document means; it reads this rule again."
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          disabled={busy || note.trim() === "" || r.review.state === "applied"}
          onClick={async () => {
            setBusy(true);
            await props.onAskAgain(r.id, note);
            setBusy(false);
          }}
        >
          Ask again with this note
        </button>
      </section>
    </article>
  );
}

function ValidationsPane({ view, onReview }: Props) {
  const list = view.plan.validations ?? [];
  if (list.length === 0) return <p className="muted imp-empty">The document asks for no check of the message.</p>;
  return (
    <div className="imp-cards">
      <p className="imp-help">
        Checks the document asks for: a <strong>reject</strong> check stops the message, a <strong>warn</strong> check only
        reports. They become the <code>validations:</code> section of the mapping.
      </p>
      {view.plan.schema_validation && (
        <p className="muted">
          Validate against the JSON Schema: input {view.plan.schema_validation.input ? "yes" : "no"}, output{" "}
          {view.plan.schema_validation.output ? "yes" : "no"}.
        </p>
      )}
      {list.map((v) => (
        <article key={v.id} className="imp-rule">
          <header>
            <h3>
              {v.code} <span className="muted">{v.side}</span> <span className={`imp-state ${v.action}`}>{v.action}</span>
            </h3>
            <div>
              <Chip confidence={v.confidence} /> <Flags confidence={v.confidence} />
            </div>
            <ReviewButtons state={v.review.state ?? "pending"} onSet={(s) => void onReview("validation", v.id, s)} />
          </header>
          <Evidence item={v} />
          <p>{v.interpretation}</p>
          <div>
            Must hold: <code>{v.expect}</code>
          </div>
          {v.message && <div className="muted">Message: {v.message}</div>}
          {(v.check as { ok?: boolean; errors?: string[] } | undefined)?.ok === false && (
            <div className="lookup-issue error">
              {((v.check as { errors?: string[] }).errors ?? []).map((e) => (
                <div key={e}>{e}</div>
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

function LookupsPane({ view }: { view: PlanView }) {
  const list = view.plan.lookups ?? [];
  if (list.length === 0) return <p className="muted imp-empty">No lookup table.</p>;
  return (
    <div className="imp-cards">
      {list.map((l) => (
        <article key={l.name} className="imp-rule">
          <h3>
            @{l.name} <span className={`imp-state ${l.status}`}>{l.status.replace("_", " ")}</span>
          </h3>
          {(l.status === "missing" || l.status === "partial") && (
            <p className="lookup-issue warning">
              The document does not give all the entries: the table is written {l.status === "missing" ? "empty" : "with what it gives"}
              and the rule finds nothing for the rest. Fill it in the mapping's Lookups tab after applying.
            </p>
          )}
          {l.entries && Object.keys(l.entries).length > 0 && (
            <table>
              <tbody>
                {Object.entries(l.entries).map(([k, v]) => (
                  <tr key={k}>
                    <td>
                      <code>{k}</code>
                    </td>
                    <td>{JSON.stringify(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {l.location && <div className="muted">{locationText(l.location)}</div>}
        </article>
      ))}
    </div>
  );
}

const TRUST: Record<string, string> = {
  paired_in_document: "input and output are given together in the document",
  inferred_pairing: "input and output come from different places: the pairing is a guess",
  single_value: "a single value, not a whole case",
};

function CasesPane({ view }: { view: PlanView }) {
  const list = view.plan.tests ?? [];
  if (list.length === 0) return <p className="muted imp-empty">The document holds no worked example.</p>;
  return (
    <div className="imp-cards">
      {list.map((t) => (
        <article key={t.id} className="imp-rule">
          <h3>
            {t.id}{" "}
            <span className={`imp-state ${t.result === "pass" ? "applied" : t.result === "fail" || t.result === "error" ? "rejected" : ""}`}>
              {(t.result ?? "not_run").replace("_", " ")}
            </span>
          </h3>
          <div className="muted">
            {locationText(t.origin)} — {TRUST[t.trust]}
            {t.partial ? "; only part of the output is given" : ""}
          </div>
          {t.detail && <pre className="imp-code">{t.detail}</pre>}
          {t.expected_rejected && <div>Expected to be rejected by: {t.expected_rejected.join(", ")}</div>}
          {t.expected_warnings && <div>Expected warnings: {t.expected_warnings.join(", ")}</div>}
          <details>
            <summary>Input and expected output</summary>
            <pre className="imp-code">{JSON.stringify(t.input, null, 2)}</pre>
            <pre className="imp-code">{JSON.stringify(t.expected, null, 2)}</pre>
          </details>
        </article>
      ))}
    </div>
  );
}

function DiscrepancyLine({ d }: { d: Discrepancy }) {
  return (
    <div className={`imp-discrepancy ${d.severity}`}>
      <span className={`imp-chip sev-${d.severity}`}>{d.severity}</span> {d.detail}
      {(d.paths ?? []).length > 0 && (
        <span className="muted">
          {" "}
          — {d.paths?.map((p) => <code key={p}>{p} </code>)}
        </span>
      )}
      {(d.locations ?? []).length > 0 && <span className="muted"> ({d.locations?.map(locationText).join("; ")})</span>}
    </div>
  );
}

function DiscrepanciesPane({ view }: { view: PlanView; onOpen: () => void }) {
  const order = { error: 0, warning: 1, info: 2 } as const;
  const list = [...view.plan.discrepancies].sort((a, b) => order[a.severity] - order[b.severity]);
  if (list.length === 0) return <p className="muted imp-empty">Nothing found between the document, the schemas and the cases.</p>;
  return (
    <div className="imp-cards">
      <p className="imp-help">What the document says that the schemas or its own cases do not.</p>
      {list.map((d, i) => (
        <div key={i}>
          <div className="muted">{d.kind.replace(/_/g, " ")}</div>
          <DiscrepancyLine d={d} />
        </div>
      ))}
    </div>
  );
}

const REASON: Record<string, string> = {
  header_or_title: "title or header",
  not_a_rule: "not a rule",
  removed_in_document: "removed in the document",
  outside_selected_mapping: "belongs to another mapping",
  unreadable: "unreadable",
  needs_user_input: "waiting for an answer",
  footnote_or_definition_used_by_a_rule: "a definition a rule uses",
  other: "other",
};

function CoveragePane({ view }: { view: PlanView }) {
  const c = view.plan.coverage;
  if (!c) return <p className="muted imp-empty">The assistant did not report the coverage.</p>;
  const total = c.units_total ?? 0;
  const part = (n: number | undefined) => (total ? `${((n ?? 0) / total) * 100}%` : "0%");
  const left = Math.max(0, total - (c.imported ?? 0) - (c.imported_with_doubt ?? 0));
  return (
    <div className="imp-cards">
      <p>
        {total} unit(s) in the document: {c.imported ?? 0} imported, {c.imported_with_doubt ?? 0} imported with doubt, {left} not
        imported. Nothing is dropped silently.
      </p>
      <div className="imp-bar" role="img" aria-label="Coverage">
        <span className="ok" style={{ width: part(c.imported) }} />
        <span className="doubt" style={{ width: part(c.imported_with_doubt) }} />
        <span className="left" style={{ width: part(left) }} />
      </div>
      {(c.not_imported ?? []).length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Where</th>
              <th>Why not</th>
            </tr>
          </thead>
          <tbody>
            {c.not_imported?.map((n, i) => (
              <tr key={i}>
                <td>{locationText(n.location)}</td>
                <td>
                  {REASON[n.reason] ?? n.reason}
                  {n.detail ? <span className="muted"> — {n.detail}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SetupPane({ view }: { view: PlanView }) {
  const p = view.plan;
  return (
    <div className="imp-cards">
      <h4>Schemas</h4>
      {(["input", "output"] as const).map((k) => (
        <div key={k}>
          {k}: {p.schemas[k].origin.replace(/_/g, " ")}
          {p.schemas[k].path ? <code> {p.schemas[k].path}</code> : null}
          {p.schemas[k].origin === "inferred" && <span className="lookup-issue warning"> inferred from the document: a proposal to confirm</span>}
          {p.schemas[k].origin === "none" && <span className="lookup-issue warning"> no schema: no path was verified</span>}
        </div>
      ))}
      <h4>Document</h4>
      <div>
        {p.document.file} — version {p.document.version.resolved} <span className="muted">({p.document.version.origin.replace(/_/g, " ")})</span>
      </div>
      {(p.document.version.candidates ?? []).length > 1 && (
        <div className="muted">
          Versions found: {p.document.version.candidates?.map((c) => `${c.value} (${c.origin.replace(/_/g, " ")})`).join(", ")}
        </div>
      )}
      {(p.document.mappings_found ?? []).length > 1 && (
        <div className="muted">
          Mappings in the document:{" "}
          {p.document.mappings_found?.map((m) => `${m.id}${m.imported ? " (imported)" : ""}`).join(", ")}
        </div>
      )}
      <h4>Profile</h4>
      {view.profile ? (
        <>
          <div>
            {view.profile.name} <span className="muted">{p.profile?.origin?.replace(/_/g, " ")}</span>
          </div>
          <pre className="imp-code">{view.profile.text}</pre>
        </>
      ) : (
        <p className="muted">No profile.</p>
      )}
    </div>
  );
}
