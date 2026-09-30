import type { ColDef, ICellRendererParams, ValueSetterParams } from "ag-grid-community";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { AgGridReact } from "ag-grid-react";
import { type Choice, Confirm } from "./Confirm";
import { ProjectButton } from "./ProjectButton";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  checkTree,
  chooseProject,
  editTree,
  initialProject,
  listFnFiles,
  type CommandReport,
  type PythonStatus,
  pythonStatus,
  readFn,
  runMapper,
  writeFn,
} from "./api";
import {
  columnOf,
  diagnosticsByRule,
  expressionOf,
  flatten,
  type Diagnostic,
  type FunctionalFile,
  nameOf,
  pushRecent,
  rowIssues,
  treePrefix,
  visibleRows,
  ruleAt,
  reviewState,
  type Row,
  setExpression,
  sourceOf,
} from "./model";

// Boolean columns only make sense on field rules; elsewhere the cell stays empty.
const fieldOnly = (p: { data?: Row }) =>
  p.data?.rule.kind === "field" ? undefined : { component: () => null };

/** A boolean setting remembered across runs (per-viewer convenience only). */
function usePersisted(key: string): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => {
    try {
      return localStorage.getItem(key) === "1";
    } catch {
      return false;
    }
  });
  const set = (next: boolean) => {
    setValue(next);
    try {
      localStorage.setItem(key, next ? "1" : "0");
    } catch {
      /* not persisted */
    }
  };
  return [value, set];
}

function loadRecent(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem("recentProjects") ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((d): d is string => typeof d === "string") : [];
  } catch {
    return [];
  }
}

const COMMANDS = ["transpile", "build", "check"] as const;

export function App() {
  const [python, setPython] = useState<PythonStatus | null>(null);
  const [project, setProject] = useState<string | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [tree, setTree] = useState<FunctionalFile | null>(null);
  const [saved, setSaved] = useState("");
  const [report, setReport] = useState<CommandReport | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<Diagnostic[]>([]);
  const [recent, setRecent] = useState<string[]>(loadRecent);
  const grid = useRef<AgGridReact<Row>>(null);
  const [question, setQuestion] = useState<{
    message: string;
    choices: Choice[];
    resolve: (id: string) => void;
  } | null>(null);
  const dirtyRef = useRef(false);
  const saveRef = useRef<() => Promise<boolean>>(async () => true);
  const folding = useRef(false);
  const treeRef = useRef<FunctionalFile | null>(null);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [showIds, setShowIds] = usePersisted("showRuleIds");
  const [developerMode, setDeveloperMode] = usePersisted("developerMode");

  useEffect(() => {
    pythonStatus().then(setPython, (e) => setStatus(String(e)));
  }, []);

  treeRef.current = tree;
  const dirty = tree !== null && JSON.stringify(tree) !== saved;
  dirtyRef.current = dirty;

  const ask = useCallback(
    (message: string, choices: Choice[]) =>
      new Promise<string>((resolve) => setQuestion({ message, choices, resolve })),
    [],
  );

  /** True when it is fine to go on: nothing unsaved, or the user saved / chose to discard. */
  const guardUnsaved = useCallback(
    async (message: string, discardLabel: string): Promise<boolean> => {
      if (!dirtyRef.current) return true;
      const choice = await ask(message, [
        { id: "save", label: "Save", primary: true },
        { id: "discard", label: discardLabel },
        { id: "cancel", label: "Cancel" },
      ]);
      if (choice === "save") return saveRef.current();
      return choice === "discard";
    },
    [ask],
  );
  const guardRef = useRef(guardUnsaved);
  guardRef.current = guardUnsaved;

  // closing the window with unsaved changes
  useEffect(() => {
    const window = getCurrentWindow();
    const unlisten = window.onCloseRequested(async (event) => {
      if (!dirtyRef.current) return;
      event.preventDefault();
      const ok = await guardRef.current(
        "Save the document? If you close without saving you will lose your changes.",
        "Close without saving",
      );
      if (ok) await window.destroy();
    });
    return () => {
      void unlisten.then((fn) => fn());
    };
  }, []);
  const canBuild = python?.available === true && project !== null && !busy;

  const load = useCallback(
    async (file: string) => {
      if (!project) return;
      try {
        const loaded = await readFn(project, file);
        setCurrent(file);
        setTree(loaded);
        setSaved(JSON.stringify(loaded));
        setStatus("");
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [project],
  );

  const openDir = useCallback(async (dir: string) => {
    try {
      const found = await listFnFiles(dir);
      setProject(dir);
      setCollapsed(new Set());
      setRecent((old) => {
        const next = pushRecent(old, dir);
        try {
          localStorage.setItem("recentProjects", JSON.stringify(next));
        } catch {
          /* not persisted */
        }
        return next;
      });
      setFiles(found);
      setCurrent(null);
      setTree(null);
      setReport(null);
      setStatus(found.length ? "" : "no mappings/functional/*.fn.yaml in this project");
      if (found.length) {
        const first = await readFn(dir, found[0]);
        setCurrent(found[0]);
        setTree(first);
        setSaved(JSON.stringify(first));
      }
    } catch (e) {
      setStatus(String(e));
    }
  }, []);

  const switchGuard = useCallback(
    () => guardRef.current("Save the current file before switching? Your unsaved changes will be lost otherwise.", "Discard changes"),
    [],
  );

  const openProject = useCallback(async () => {
    if (!(await switchGuard())) return;
    const dir = await chooseProject(recent[0]);
    if (dir) await openDir(dir);
  }, [openDir, recent, switchGuard]);

  useEffect(() => {
    initialProject().then(
      (dir) => {
        if (dir) void openDir(dir);
      },
      () => {},
    );
  }, [openDir]);

  const save = useCallback(async (): Promise<boolean> => {
    if (!project || !current || !tree) return true;
    setBusy(true);
    try {
      const decayed = await writeFn(project, current, tree);
      await load(current);
      setStatus(
        decayed.length
          ? `saved; validation reset on: ${decayed.join(", ")}`
          : "saved",
      );
      return true;
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
      return false;
    } finally {
      setBusy(false);
    }
  }, [project, current, tree, load]);
  saveRef.current = save;

  const run = useCallback(
    async (command: string) => {
      if (!project) return;
      // the commands read the files on disk, not what is in the grid
      if (!(await guardRef.current("Save before continuing?", "Continue without saving"))) return;
      setBusy(true);
      try {
        setReport(await runMapper(project, command));
      } catch (e) {
        setStatus(String(e));
      } finally {
        setBusy(false);
      }
    },
    [project],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (dirty && !busy) void save();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dirty, busy, save]);

  const edit = useCallback((path: string, change: (rule: NonNullable<ReturnType<typeof ruleAt>>) => void) => {
    setTree((old) => {
      if (!old) return old;
      const copy = structuredClone(old);
      const rule = ruleAt(copy, path);
      if (rule) change(rule);
      return copy;
    });
  }, []);

  /** Target / Source edits are done by the Python worker (one implementation of the path rules). */
  const remoteEdit = useCallback(
    async (op: "retarget" | "set_source", path: string, value: string) => {
      const current = treeRef.current;
      if (!current) return;
      try {
        setTree(await editTree(current, op, path, value));
        setStatus("");
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [],
  );

  const rows = useMemo(
    () => (tree ? visibleRows(flatten(tree.rules), collapsed) : []),
    [tree, collapsed],
  );
  const toggleFold = useCallback((path: string) => {
    setCollapsed((old) => {
      const next = new Set(old);
      if (!next.delete(path)) next.add(path);
      return next;
    });
  }, []);
  // check the rules as they are edited (debounced), against the project's schemas
  useEffect(() => {
    if (!tree || !project || !current || python?.available !== true) {
      setLive([]);
      return;
    }
    const stem = current.replace(/^.*\//, "").replace(/\.fn\.yaml$/, "");
    let stale = false;
    const timer = setTimeout(() => {
      checkTree(tree, project, stem).then(
        (found) => {
          if (!stale) setLive(found);
        },
        () => {},
      );
    }, 150);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [tree, project, current, python]);

  const diagnostics = useMemo(
    () =>
      diagnosticsByRule(
        [...live, ...(current && report ? report.diagnostics : [])],
        current ?? "",
      ),
    [current, report, live],
  );

  /** Columns (by colId) with an error on this row; "*" = the whole row. */
  const invalidColumns = useCallback(
    (path: string): Set<string> => {
      const found = new Set<string>();
      for (const d of diagnostics.get(path) ?? []) {
        if (d.severity === "error") found.add(columnOf(d) ?? "*");
      }
      return found;
    },
    [diagnostics],
  );

  // row / cell classes are computed from the diagnostics: redraw when they change
  useEffect(() => {
    grid.current?.api?.redrawRows();
  }, [diagnostics]);

  const columns = useMemo<ColDef<Row>[]>(() => {
    const isField = (r?: Row) => r?.rule.kind === "field";
    const editableFor = (kinds: string[]) => (p: { data?: Row }) =>
      p.data !== undefined && kinds.includes(p.data.rule.kind);
    return [
      {
        headerName: "",
        colId: "warn",
        width: 56,
        pinned: "left",
        sortable: false,
        resizable: false,
        cellClass: "warn-cell",
        valueGetter: (p) =>
          p.data && rowIssues(p.data.rule, diagnostics.get(p.data.path) ?? []).length ? "⚠️" : "",
        tooltipValueGetter: (p) =>
          p.data ? rowIssues(p.data.rule, diagnostics.get(p.data.path) ?? []).join("\n") : "",
      },
      { headerName: "Id", colId: "id", hide: !showIds, valueGetter: (p) => p.data?.rule.id ?? "", width: 100 },
      {
        headerName: "Target",
        colId: "target",
        width: 200,
        editable: (p) => !folding.current && p.data?.rule.kind !== "lookup",
        valueGetter: (p) => (p.data ? nameOf(p.data.rule, p.data.depth) : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          void remoteEdit("retarget", p.data.path, String(p.newValue ?? ""));
          return true;
        },
        cellRenderer: (p: ICellRendererParams<Row>) =>
          p.data ? (
            <span>
              <span className="tree">{treePrefix(p.data)}</span>
              {p.data.hasChildren ? (
                <span
                  className="fold"
                  title={collapsed.has(p.data.path) ? "Expand" : "Collapse"}
                  onMouseDown={() => {
                    // the grid starts editing on the click that follows; tell it not to
                    folding.current = true;
                    setTimeout(() => (folding.current = false), 300);
                  }}
                  onClick={() => toggleFold(p.data!.path)}
                >
                  {collapsed.has(p.data.path) ? "▸" : "▾"}
                </span>
              ) : null}
              {p.value}
            </span>
          ) : null,
      },
      { headerName: "Kind",
        colId: "kind", valueGetter: (p) => p.data?.rule.kind, width: 80 },
      {
        headerName: "Type",
        colId: "type",
        width: 90,
        editable: editableFor(["field"]),
        cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: ["str", "int", "number", "bool", "date", "datetime"] },
        valueGetter: (p) => {
          const rule = p.data?.rule;
          if (rule?.kind === "field") return rule.type;
          return rule?.kind === "loop" ? "array" : rule?.kind === "object" ? "object" : "";
        },
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.type = String(p.newValue);
          });
          return true;
        },
      },
      {
        headerName: "Req.",
        colId: "req",
        width: 70,
        editable: editableFor(["field"]),
        cellDataType: "boolean",
        cellRendererSelector: fieldOnly,
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.required : null),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.required = Boolean(p.newValue);
          });
          return true;
        },
      },
      {
        headerName: "Source",
        colId: "source",
        width: 200,
        editable: editableFor(["field", "loop"]),
        valueGetter: (p) => (p.data ? sourceOf(p.data.rule) : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          void remoteEdit("set_source", p.data.path, String(p.newValue ?? ""));
          return true;
        },
      },
      {
        headerName: "Expression / filter / guard",
        colId: "expression",
        flex: 1,
        minWidth: 260,
        editable: editableFor(["field", "loop", "object"]),
        valueGetter: (p) => (p.data ? expressionOf(p.data.rule) : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => setExpression(r, String(p.newValue ?? "")));
          return true;
        },
      },
      {
        headerName: "Description",
        colId: "description",
        width: 260,
        editable: true,
        valueGetter: (p) => p.data?.rule.description ?? "",
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            r.description = String(p.newValue ?? "") || null;
          });
          return true;
        },
      },
      {
        headerName: "Status",
        colId: "status",
        hide: !developerMode,
        width: 80,
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.transform.status : ""),
      },
      {
        headerName: "Validated",
        colId: "validated",
        width: 100,
        editable: editableFor(["field"]),
        cellDataType: "boolean",
        cellRendererSelector: fieldOnly,
        valueGetter: (p) => (isField(p.data) && p.data?.rule.kind === "field" ? p.data.rule.validation.validated : null),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind !== "field") return;
            r.validation.validated = Boolean(p.newValue);
            if (r.validation.validated) r.validation.needs_review = false;
          });
          return true;
        },
      },
      {
        headerName: "Review",
        colId: "review",
        width: 90,
        editable: editableFor(["field"]),
        cellDataType: "boolean",
        cellRendererSelector: fieldOnly,
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.validation.needs_review : null),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.validation.needs_review = Boolean(p.newValue);
          });
          return true;
        },
      },
      {
        headerName: "Notes",
        colId: "notes",
        width: 220,
        editable: editableFor(["field"]),
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.validation.notes ?? "" : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.validation.notes = String(p.newValue ?? "") || null;
          });
          return true;
        },
      },
    ];
  }, [edit, remoteEdit, showIds, developerMode, diagnostics, collapsed, toggleFold]);

  return (
    <div className="app">
      <header>
        <ProjectButton recent={recent} onOpen={openProject} onPick={async (d) => {
            if (await switchGuard()) await openDir(d);
          }} />
        <span className="project">{project ?? "no project"}</span>
        <span className="spacer" />
        <button disabled={!dirty || busy} onClick={() => void save()}>
          Save{dirty ? " ●" : ""}
        </button>
        {COMMANDS.map((c) => (
          <button key={c} disabled={!canBuild} onClick={() => run(c)}>
            {c[0].toUpperCase() + c.slice(1)}
          </button>
        ))}
      </header>
      {python && !python.available && (
        <div className="banner">
          Read-only: {python.reason} Build, check and save are disabled.
        </div>
      )}
      <div className="body">
        <nav>
          <button
            className="project-properties"
            disabled={!project}
            onClick={() => setStatus("Project properties (mapper.toml) are not editable here yet")}
          >
            Project properties…
          </button>
          {files.map((f) => (
            <div
              key={f}
              className={f === current ? "file current" : "file"}
              onClick={async () => {
                if (f !== current && (await switchGuard())) await load(f);
              }}
            >
              {f.replace("mappings/functional/", "")}
            </div>
          ))}
        </nav>
        <main>
          {tree ? (
            <AgGridReact<Row>
              rowData={rows}
              columnDefs={columns}
              getRowId={(p) => p.data.path}
              ref={grid}
              tooltipShowDelay={200}
              defaultColDef={{
                cellClassRules: {
                  "cell-invalid": (p) => {
                    const cols = invalidColumns(p.data?.path ?? "");
                    return cols.has(p.column.getColId()) || cols.has("*");
                  },
                },
              }}
              singleClickEdit
              stopEditingWhenCellsLoseFocus
              rowClassRules={{
                "row-error": (p) =>
                  (diagnostics.get(p.data?.path ?? "") ?? []).some((d: { severity: string }) => d.severity === "error"),
                "row-warning": (p) =>
                  (diagnostics.get(p.data?.path ?? "") ?? []).some((d: { severity: string }) => d.severity === "warning"),
                "row-review": (p) => (p.data ? reviewState(p.data.rule) === "review" : false),
                "row-validated": (p) => (p.data ? reviewState(p.data.rule) === "validated" : false),
              }}
            />
          ) : (
            <div className="empty">{project ? "Pick a mapping" : "Open a project to begin"}</div>
          )}
        </main>
      </div>
      <div className="switches">
        <label>
          <input type="checkbox" checked={showIds} onChange={(e) => setShowIds(e.target.checked)} />
          Show rule ids
        </label>
        <label>
          <input
            type="checkbox"
            checked={developerMode}
            onChange={(e) => setDeveloperMode(e.target.checked)}
          />
          Developer mode
        </label>
      </div>
      {question && (
        <Confirm
          message={question.message}
          choices={question.choices}
          onChoose={(id) => {
            question.resolve(id);
            setQuestion(null);
          }}
        />
      )}
      <footer>
        <div className="status">{status}</div>
        {(diagnostics.get("") ?? []).map((d, i) => (
          <div key={`f${i}`} className={d.severity}>
            {d.severity}: {d.message}
          </div>
        ))}
        {report && (
          <div className={report.ok ? "report ok" : "report failed"}>
            {report.messages.map((m, i) => (
              <div key={`m${i}`}>{m}</div>
            ))}
            {report.diagnostics.map((d, i) => (
              <div key={`d${i}`} className={d.severity}>
                {d.severity}: {d.file ? `${d.file}: ` : ""}
                {d.rule ? `${d.rule}: ` : ""}
                {d.message}
              </div>
            ))}
          </div>
        )}
      </footer>
    </div>
  );
}
