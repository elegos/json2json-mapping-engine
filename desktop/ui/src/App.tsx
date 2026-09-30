import type { CellClassParams, ColDef, ValueSetterParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  chooseProject,
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
  diagnosticsByRule,
  expressionOf,
  flatten,
  type FunctionalFile,
  nameOf,
  ruleAt,
  reviewState,
  type Row,
  setExpression,
  setName,
  setSource,
  sourceOf,
} from "./model";

// Boolean columns only make sense on field rules; elsewhere the cell stays empty.
const fieldOnly = (p: { data?: Row }) =>
  p.data?.rule.kind === "field" ? undefined : { component: () => null };

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

  useEffect(() => {
    pythonStatus().then(setPython, (e) => setStatus(String(e)));
  }, []);

  const dirty = tree !== null && JSON.stringify(tree) !== saved;
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

  const openProject = useCallback(async () => {
    const dir = await chooseProject();
    if (dir) await openDir(dir);
  }, [openDir]);

  useEffect(() => {
    initialProject().then(
      (dir) => {
        if (dir) void openDir(dir);
      },
      () => {},
    );
  }, [openDir]);

  const save = useCallback(async () => {
    if (!project || !current || !tree) return;
    setBusy(true);
    try {
      const decayed = await writeFn(project, current, tree);
      await load(current);
      setStatus(
        decayed.length
          ? `saved; validation reset on: ${decayed.join(", ")}`
          : "saved",
      );
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }, [project, current, tree, load]);

  const run = useCallback(
    async (command: string) => {
      if (!project) return;
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

  const rows = useMemo(() => (tree ? flatten(tree.rules) : []), [tree]);
  const diagnostics = useMemo(
    () => (current && report ? diagnosticsByRule(report.diagnostics, current) : new Map()),
    [current, report],
  );

  const columns = useMemo<ColDef<Row>[]>(() => {
    const isField = (r?: Row) => r?.rule.kind === "field";
    const editableFor = (kinds: string[]) => (p: { data?: Row }) =>
      p.data !== undefined && kinds.includes(p.data.rule.kind);
    return [
      { headerName: "Rule", valueGetter: (p) => p.data?.path, width: 150, pinned: "left" },
      { headerName: "Id", valueGetter: (p) => p.data?.rule.id ?? "", width: 90 },
      { headerName: "Kind", valueGetter: (p) => p.data?.rule.kind, width: 80 },
      {
        headerName: "Name",
        width: 200,
        editable: true,
        valueGetter: (p) => (p.data ? nameOf(p.data.rule) : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => setName(r, String(p.newValue ?? "")));
          return true;
        },
        cellStyle: (p: CellClassParams<Row>) => ({ paddingLeft: `${8 + (p.data?.depth ?? 0) * 18}px` }),
      },
      {
        headerName: "Type",
        width: 90,
        editable: editableFor(["field"]),
        cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: ["str", "int", "number", "bool", "date", "datetime"] },
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.type : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => {
            if (r.kind === "field") r.type = String(p.newValue);
          });
          return true;
        },
      },
      {
        headerName: "Req.",
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
        width: 200,
        editable: editableFor(["field", "loop"]),
        valueGetter: (p) => (p.data ? sourceOf(p.data.rule) : ""),
        valueSetter: (p: ValueSetterParams<Row>) => {
          edit(p.data.path, (r) => setSource(r, String(p.newValue ?? "")));
          return true;
        },
      },
      {
        headerName: "Expression / filter / guard",
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
        headerName: "Status",
        width: 80,
        valueGetter: (p) => (p.data?.rule.kind === "field" ? p.data.rule.transform.status : ""),
      },
      {
        headerName: "Description",
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
        headerName: "Validated",
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
  }, [edit]);

  return (
    <div className="app">
      <header>
        <button onClick={openProject}>Open project…</button>
        <span className="project">{project ?? "no project"}</span>
        <span className="spacer" />
        <button disabled={!dirty || busy} onClick={save}>
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
          {files.map((f) => (
            <div
              key={f}
              className={f === current ? "file current" : "file"}
              onClick={() => void load(f)}
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
      <footer>
        <div className="status">{status}</div>
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
