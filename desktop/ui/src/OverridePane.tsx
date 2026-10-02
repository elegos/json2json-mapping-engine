import type { EditorView } from "@codemirror/view";
import { useEffect, useRef, useState } from "react";
import { setActiveCellEditor } from "./cellEditor";
import { type Proposal, proposalOf } from "./api";
import { CodeEditor, type Completer } from "./CodeEditor";
import type { FieldRule, FunctionalFile, ReviewFlag } from "./model";

interface Props {
  tree: FunctionalFile;
  path: string;
  rule: FieldRule;
  /** The rule's target with its containers (`Customer.Name`). */
  target: string;
  flag?: ReviewFlag;
  /** `take_over`, `accept_proposal`, `keep_override`: done by the worker, the tree is replaced. */
  onResolve: (op: "take_over" | "accept_proposal" | "keep_override") => void;
  /** Suggestions for the override: `root`, `src`, the schemas' fields and the functions. */
  completer: Completer;
  onCode: (code: string) => void;
  onClose: () => void;
}

/**
 * The split pane of a rule (docs/ARCHITECTURE.md, §Auto / Manual mode): what the transpiler
 * generates from the Source and expression on the left, the developer's `code_override` on the
 * right. A rule still on auto offers to take the code over; a manual one whose auto code moved
 * offers the new proposal or keeping the override.
 */
export function OverridePane({ tree, path, rule, target, flag, onResolve, completer, onCode, onClose }: Props) {
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const manual = rule.transform.status === "manual";
  // right after "Edit as code" the cursor goes into the editor; selecting another rule leaves it be
  const focusNext = useRef(false);
  const codeView = useRef<EditorView | null>(null);
  // the function explorer can put a call into the override while it is shown
  useEffect(
    () => (manual && codeView.current ? setActiveCellEditor(codeView.current, "code") : undefined),
    [manual, path, rule.transform.last_auto_version],
  );
  useEffect(() => {
    focusNext.current = false;
  }, [path]);
  // the auto code depends on the functional side only, not on the override being typed
  const functional = JSON.stringify([rule.source_path, rule.source_constant, rule.has_constant, rule.transform.expression]);

  useEffect(() => {
    let stale = false;
    const timer = setTimeout(() => {
      proposalOf(tree, path).then(
        (found) => {
          if (stale) return;
          setProposal(found);
          setFailure(null);
        },
        (e) => !stale && setFailure(String(e instanceof Error ? e.message : e)),
      );
    }, 150);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
    // the tree changes with every keystroke of the override: ask again only for the functional side
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, functional, manual]);

  const auto = proposal?.auto ?? null;
  const why = failure ?? proposal?.error ?? null;
  return (
    <section className="override-pane">
      <header>
        <strong>{target}</strong>
        <span className="muted">{manual ? "manual override" : "auto"}</span>
        {flag?.stale_override && <span className="stale">the auto code changed since the override was taken</span>}
        <span className="grow" />
        {manual && flag?.stale_override && (
          <button onClick={() => onResolve("keep_override")}>Keep override</button>
        )}
        {manual ? (
          <button onClick={() => onResolve("accept_proposal")} disabled={auto === null}>
            Use auto code
          </button>
        ) : (
          <button
            onClick={() => {
              focusNext.current = true;
              onResolve("take_over");
            }}
            disabled={auto === null}
          >
            Edit as code
          </button>
        )}
        <button onClick={onClose} title="Close">
          ×
        </button>
      </header>
      <div className="panes">
        <div className="pane">
          <h4>Auto (transpiler)</h4>
          {auto !== null ? <pre>{auto}</pre> : <div className="muted">{why ?? "…"}</div>}
        </div>
        <div className="pane">
          <h4>Override</h4>
          {manual ? (
            <CodeEditor
              key={`${path}|${rule.transform.last_auto_version}`}
              viewRef={codeView}
              className="code-editor multi"
              singleLine={false}
              highlightPython
              autoFocus={focusNext.current}
              completer={completer}
              value={rule.transform.code_override ?? ""}
              onChange={onCode}
            />
          ) : (
            <div className="muted">None: the rule follows its expression.</div>
          )}
        </div>
      </div>
    </section>
  );
}
