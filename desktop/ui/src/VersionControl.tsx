import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  type VcsConflictFile,
  type VcsState,
  vcsAbort,
  vcsCommit,
  vcsConflicts,
  vcsPull,
  vcsPush,
  vcsResolve,
  vcsState,
} from "./api";

interface Props {
  project: string;
  onClose: () => void;
  /** The files on disk changed (a pull, a settled conflict): the grid reads them again. */
  onChanged: () => void;
  /** Saves what is being edited; false when the user keeps it unsaved. */
  ensureSaved: () => Promise<boolean>;
}

type Side = "mine" | "remote";

/** How a conflicted value reads: a rule field as it is, a function as its text. */
export function show(value: unknown, missing: boolean): string {
  if (missing) return "(deleted)";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2) ?? "";
}

/** The choices still to make in `files`: items of the rules and functions files without one. */
export function pending(files: VcsConflictFile[], chosen: Record<string, Record<string, Side>>): number {
  return files
    .filter((f) => f.kind === "rules" || f.kind === "functions")
    .reduce((n, f) => n + f.items.filter((i) => !chosen[f.file]?.[i.path]).length, 0);
}

/** Git mode (docs/ARCHITECTURE.md, §Version control): what changed, the version notes, commit
 * (which checks and builds first), pull with rebase and push, and the conflicts that remain,
 * settled field by field without touching YAML. */
export function VersionControl({ project, onClose, onChanged, ensureSaved }: Props) {
  const [info, setInfo] = useState<VcsState | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const [files, setFiles] = useState<VcsConflictFile[]>([]);
  const [chosen, setChosen] = useState<Record<string, Record<string, Side>>>({});

  const refresh = useCallback(async () => {
    const next = await vcsState(project);
    setInfo(next);
    setFiles(next.rebasing || next.conflicts?.length ? await vcsConflicts(project) : []);
  }, [project]);

  const guarded = useCallback(
    async (work: () => Promise<void>) => {
      setBusy(true);
      setMessage("");
      try {
        await work();
        await refresh();
      } catch (e) {
        setMessage(String(e instanceof Error ? e.message : e));
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  useEffect(() => {
    void guarded(async () => undefined);
  }, [guarded]);

  const commit = (wip: boolean) =>
    guarded(async () => {
      if (!(await ensureSaved())) return;
      const done = await vcsCommit(project, notes, wip);
      if (done.blocked) {
        setProblems(done.problems);
        setMessage("The check failed: nothing was committed.");
        return;
      }
      setProblems([]);
      if (done.committed) {
        setNotes("");
        setMessage(`Committed ${done.commit}: ${done.subject}`);
      } else {
        setMessage(done.message ?? "Nothing to commit.");
      }
    });

  const pull = () =>
    guarded(async () => {
      if (!(await ensureSaved())) return;
      const done = await vcsPull(project);
      onChanged();
      setChosen({});
      setMessage(
        done.ok
          ? "Up to date with the remote."
          : `The pull stopped on ${done.conflicts.length} file(s) that both sides changed: settle them below.`,
      );
    });

  const push = () =>
    guarded(async () => {
      await vcsPush(project);
      setMessage("Pushed.");
    });

  const abort = () =>
    guarded(async () => {
      await vcsAbort(project);
      onChanged();
      setChosen({});
      setMessage("The pull was given up: the branch is as it was before.");
    });

  const settle = (file: VcsConflictFile) =>
    guarded(async () => {
      const done = await vcsResolve(project, file.file, chosen[file.file] ?? {});
      onChanged();
      setMessage(done.done ? "All settled: the pull is finished." : `${file.file} settled.`);
    });

  const choose = (file: string, path: string, side: Side) =>
    setChosen((old) => ({ ...old, [file]: { ...old[file], [path]: side } }));

  if (!info) {
    return createPortal(
      <div className="modal-backdrop">
        <div className="modal vcs">
          <p>{message || "Reading the repository…"}</p>
        </div>
      </div>,
      document.body,
    );
  }
  const authored = (info.changes ?? []).filter((c) => !c.generated);
  const generated = (info.changes ?? []).filter((c) => c.generated);
  const rebasing = Boolean(info.rebasing);
  const open = files.filter((f) => f.kind !== "generated");

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal vcs"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && !busy && onClose()}
      >
        <h3>Version control</h3>
        {!info.git && <p>git is not installed: there is nothing to commit with.</p>}
        {info.git && !info.repo && <p>This project is not in a git repository.</p>}
        {info.repo && (
          <>
            <p className="vcs-branch">
              Branch <b>{info.branch ?? "(detached)"}</b>
              {info.upstream
                ? ` · ${info.upstream}: ${info.ahead} ahead, ${info.behind} behind`
                : " · no upstream"}
            </p>

            {rebasing ? (
              <div className="vcs-conflicts">
                <p>
                  The pull stopped: both sides changed the same thing. For each, say which value
                  stays. Generated files are rebuilt for you.
                </p>
                {open.map((f) => (
                  <fieldset key={f.file} className="vcs-file">
                    <legend>{f.file}</legend>
                    {f.kind === "text" && (
                      <p>
                        This file cannot be settled here (it is neither a mapping nor a function
                        file). Edit it outside the tool, or give the pull up.
                      </p>
                    )}
                    {f.items.map((i) => (
                      <div key={i.path} className="vcs-item">
                        <code>{i.path}</code>
                        <div className="vcs-sides">
                          {(["mine", "remote"] as const).map((side) => (
                            <label key={side} className={chosen[f.file]?.[i.path] === side ? "on" : ""}>
                              <input
                                type="radio"
                                name={`${f.file}:${i.path}`}
                                checked={chosen[f.file]?.[i.path] === side}
                                onChange={() => choose(f.file, i.path, side)}
                              />
                              <b>{side === "mine" ? "Mine" : "Theirs (remote)"}</b>
                              <pre>
                                {side === "mine"
                                  ? show(i.mine, i.mine_missing)
                                  : show(i.remote, i.remote_missing)}
                              </pre>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                    {(f.kind === "rules" || f.kind === "functions") && (
                      <button
                        className="primary"
                        disabled={busy || f.items.some((i) => !chosen[f.file]?.[i.path])}
                        onClick={() => void settle(f)}
                      >
                        Settle {f.file}
                      </button>
                    )}
                  </fieldset>
                ))}
                {open.length > 0 && pending(open, chosen) > 0 && (
                  <p className="vcs-hint">{pending(open, chosen)} choice(s) left.</p>
                )}
              </div>
            ) : (
              <>
                <h4>Changes</h4>
                {authored.length === 0 && generated.length === 0 && <p>Nothing changed.</p>}
                <ul className="vcs-changes">
                  {authored.map((c) => (
                    <li key={c.path}>
                      <code>{c.status}</code> {c.path}
                    </li>
                  ))}
                  {generated.length > 0 && (
                    <li className="vcs-generated">
                      {generated.length} generated file(s) in build/compiled: rebuilt and committed
                      with the sources
                    </li>
                  )}
                </ul>
                <label className="vcs-notes">
                  Version notes (the first line is the title)
                  <textarea
                    rows={4}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="What changed, and why"
                  />
                </label>
                {problems.length > 0 && (
                  <div className="vcs-problems">
                    <b>The check found:</b>
                    <ul>
                      {problems.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </>
        )}
        {message && <p className="vcs-message">{message}</p>}
        <div className="modal-buttons">
          {info.repo && !rebasing && (
            <>
              <button disabled={busy} onClick={() => void pull()} title="git pull --rebase">
                Pull
              </button>
              <button disabled={busy || !info.ahead} onClick={() => void push()}>
                Push{info.ahead ? ` (${info.ahead})` : ""}
              </button>
              {problems.length > 0 && (
                <button
                  disabled={busy}
                  onClick={() => void commit(true)}
                  title="Commit the sources only, marked WIP"
                >
                  Commit as WIP
                </button>
              )}
              <button
                className="primary"
                disabled={busy || (authored.length === 0 && generated.length === 0)}
                onClick={() => void commit(false)}
                title="Checks and builds first; commits the sources and the generated files together"
              >
                Commit
              </button>
            </>
          )}
          {rebasing && (
            <button disabled={busy} onClick={() => void abort()}>
              Give up the pull
            </button>
          )}
          <button disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
