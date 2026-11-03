import { useState } from "react";
import {
  type Draft,
  type PlanQuestion,
  type PlanView,
  answersFrom,
  isNote,
  isOpen,
  locationText,
  questionOrder,
  ruleCountOf,
} from "./importModel";

interface Props {
  /** The plan, for the questions and the rules they touch; or give `questions` and `ruleLabel`. */
  view?: PlanView;
  questions?: PlanQuestion[];
  ruleLabel?: (id: string) => string;
  /** While a run goes on: the answers are written now and the run reads them; no run is started. */
  live?: boolean;
  /** Writes the answers into the plan (and, unless `live`, starts the next run). */
  onSubmit: (answers: { id: string; answer?: string; skip?: boolean }[]) => Promise<void>;
  /** Look at the plan as it is, without answering. */
  onSkipToReview?: () => void;
}

const SCOPE: Record<PlanQuestion["scope"], string> = {
  profile: "kept in the profile, for every document of this kind",
  mapping: "kept in this import",
  rule: "about one rule",
};

/** What the assistant could not decide, one card each, the ones that touch most rules first. */
export function ImportQuestions({ view, questions, ruleLabel: labelOf, live, onSubmit, onSkipToReview }: Props) {
  const [drafts, setDrafts] = useState<Record<string, Draft | undefined>>({});
  const [busy, setBusy] = useState(false);
  const all = questionOrder((questions ?? view?.plan.questions ?? []).filter((q) => !isNote(q)));
  const open = all.filter(isOpen);
  const answers = answersFrom(open, drafts);
  const set = (id: string, d: Draft | undefined) => setDrafts((old) => ({ ...old, [id]: d }));
  const ruleLabel = (id: string) => labelOf?.(id) ?? view?.plan.rules.find((r) => r.id === id)?.target.path ?? id;

  return (
    <div className={live ? "imp-questions imp-live" : "imp-questions"}>
      <h3>
        {open.length} question{open.length === 1 ? "" : "s"} for you
      </h3>
      <p className="imp-help">
        {live
          ? "The run does not wait: until you answer, the rules that depend on a question use the proposal and are marked as guesses. An answer you give now is read by the batches that come next, and the rules it touches are read again at the end."
          : "Each answer is used for every rule it touches. A question you skip is read the way the assistant proposes, and the rules that depend on it are marked as guesses. The questions come back with the next run only if they are still open."}
      </p>
      {open.map((q, n) => {
        const d = drafts[q.id];
        const typed = d && !d.skip && !(q.options ?? []).includes(d.answer) ? d.answer : "";
        return (
          <section key={q.id} className="imp-question" aria-label={`Question ${n + 1}`}>
            <div className="imp-qhead">
              <strong>{q.text}</strong>
              <span className="imp-scope">{q.scope}</span>
            </div>
            <div className="muted imp-qmeta">
              {q.topic} — {SCOPE[q.scope]}
            </div>
            {(q.evidence ?? []).map((e, i) => (
              <blockquote key={i} className="imp-evidence">
                {e.text}
                {e.location && <cite> — {locationText(e.location)}</cite>}
              </blockquote>
            ))}
            {ruleCountOf(q) > 0 && (
              <details className="imp-affects">
                <summary>
                  Touches {ruleCountOf(q)} rule{ruleCountOf(q) === 1 ? "" : "s"}
                </summary>
                <ul>
                  {(q.rule_ids ?? []).map((id) => (
                    <li key={id}>
                      <code>{ruleLabel(id)}</code>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <div role="radiogroup" aria-label="Answer" className="imp-options">
              {(q.options ?? []).map((o) => (
                <label key={o} className="modal-option">
                  <input
                    type="radio"
                    name={q.id}
                    checked={d !== undefined && !d.skip && d.answer === o}
                    onChange={() => set(q.id, { answer: o, skip: false })}
                  />
                  {o}
                  {o === q.proposal && <span className="imp-proposed"> proposed</span>}
                </label>
              ))}
              <label className="modal-option">
                <input
                  type="radio"
                  name={q.id}
                  checked={d?.skip === true}
                  onChange={() => set(q.id, { answer: "", skip: true })}
                />
                I don't know — {q.proposal ? <>assume: <em>{q.proposal}</em></> : "let the assistant assume"}
              </label>
              <label className="imp-other">
                <span>{(q.options ?? []).length ? "Something else" : "Your answer"}</span>
                <textarea
                  rows={2}
                  value={typed}
                  placeholder={q.proposal && !(q.options ?? []).length ? q.proposal : ""}
                  onChange={(e) => set(q.id, e.target.value === "" ? undefined : { answer: e.target.value, skip: false })}
                />
              </label>
              {q.proposal && !(q.options ?? []).includes(q.proposal) && (
                <button className="link" onClick={() => set(q.id, { answer: q.proposal ?? "", skip: false })}>
                  Use the proposal as the answer
                </button>
              )}
            </div>
          </section>
        );
      })}
      {all.filter((q) => !isOpen(q)).length > 0 && (
        <details className="imp-answered">
          <summary>{all.length - open.length} answered</summary>
          {all
            .filter((q) => !isOpen(q))
            .map((q) => (
              <p key={q.id}>
                {q.text}
                <br />
                <span className="muted">
                  {q.status === "skipped_assumed_proposal" ? `skipped, assumed: ${q.proposal ?? "the proposal"}` : q.answer}
                </span>
              </p>
            ))}
        </details>
      )}
      <div className="modal-buttons imp-qfoot">
        {onSkipToReview && <button onClick={onSkipToReview}>Look at the plan first</button>}
        <button
          className="primary"
          disabled={busy || answers.length === 0}
          onClick={async () => {
            setBusy(true);
            try {
              await onSubmit(answers);
              setDrafts({});
            } finally {
              setBusy(false);
            }
          }}
        >
          {live
            ? `Send ${answers.length} answer${answers.length === 1 ? "" : "s"}`
            : `Send ${answers.length} answer${answers.length === 1 ? "" : "s"} and continue`}
        </button>
      </div>
    </div>
  );
}
