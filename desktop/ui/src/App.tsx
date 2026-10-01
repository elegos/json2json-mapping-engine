import type { ColDef, ICellRendererParams, ValueSetterParams } from "ag-grid-community";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { AgGridReact } from "ag-grid-react";
import { type Choice, Confirm } from "./Confirm";
import { CompletingCellEditor, type GridContext } from "./CompletingCellEditor";
import { Lookups } from "./Lookups";
import { Paths } from "./Paths";
import { ProjectProperties } from "./ProjectProperties";
import {
  type ConfigIssue,
  type ConfigSchema,
  type ConfigValues,
} from "./projectConfig";
import { ProjectButton } from "./ProjectButton";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  changeStructure,
  checkTree,
  completeAt,
  configCheck,
  configRead,
  configWrite,
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
  changedColumns,
  columnOf,
  descendants,
  insertionPoint,
  diagnosticsByRule,
  expressionOf,
  filterRows,
  flatten,
  type Diagnostic,
  type FunctionalFile,
  type LookupRule,
  nameOf,
  pushRecent,
  rowIssues,
  savedIndex,
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
  const [filterText, setFilterText] = useState("");
  const filterInput = useRef<HTMLInputElement>(null);
  const [view, setView] = useState<"rules" | "lookups" | "paths" | "project">("rules");
  // mapper.toml: the form's descriptors, the file's values, the draft being edited
  const [configSchema, setConfigSchema] = useState<ConfigSchema | null>(null);
  const [configSaved, setConfigSaved] = useState("");
  const [config, setConfig] = useState<ConfigValues | null>(null);
  const [configIssues, setConfigIssues] = useState<ConfigIssue[]>([]);
  // undo / redo: snapshots of what the user can edit (the rules and the mapper.toml draft)
  type Snapshot = { tree: FunctionalFile | null; config: ConfigValues | null };
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const configRef = useRef<ConfigValues | null>(null);
  const lastEdit = useRef({ key: "", at: 0 });
  const [, setHistoryVersion] = useState(0);
  const [showIds, setShowIds] = usePersisted("showRuleIds");
  const [developerMode, setDeveloperMode] = usePersisted("developerMode");

  useEffect(() => {
    pythonStatus().then(setPython, (e) => setStatus(String(e)));
  }, []);

  treeRef.current = tree;
  configRef.current = config;
  const fnDirty = tree !== null && JSON.stringify(tree) !== saved;
  const configDirty = config !== null && JSON.stringify(config) !== configSaved;
  const dirty = fnDirty || configDirty;
  dirtyRef.current = dirty;

  /**
   * Remember the state before a change. Edits with the same `key` in quick succession
   * (typing in one field) count as one step.
   */
  const remember = useCallback((before: FunctionalFile | null = treeRef.current, key = "") => {
    const now = Date.now();
    const same = key !== "" && lastEdit.current.key === key && now - lastEdit.current.at < 800;
    lastEdit.current = { key, at: now };
    if (!same) past.current.push({ tree: before, config: configRef.current });
    future.current = [];
    setHistoryVersion((v) => v + 1);
  }, []);
  const forgetHistory = useCallback(() => {
    past.current = [];
    future.current = [];
    lastEdit.current = { key: "", at: 0 };
    setHistoryVersion((v) => v + 1);
  }, []);
  const travel = useCallback((from: Snapshot[], to: Snapshot[]) => {
    const target = from.pop();
    if (!target) return;
    to.push({ tree: treeRef.current, config: configRef.current });
    lastEdit.current = { key: "", at: 0 };
    setTree(target.tree);
    if (target.config && configRef.current) setConfig(target.config);
    setHistoryVersion((v) => v + 1);
  }, []);
  const undo = useCallback(() => travel(past.current, future.current), [travel]);
  const redo = useCallback(() => travel(future.current, past.current), [travel]);
  const canUndo = past.current.length > 0;
  const canRedo = future.current.length > 0;

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
    async (file: string, keepHistory = false) => {
      if (!project) return;
      try {
        const loaded = await readFn(project, file);
        if (!keepHistory) forgetHistory();
        setCurrent(file);
        setTree(loaded);
        setSaved(JSON.stringify(loaded));
        setStatus("");
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [project, forgetHistory],
  );

  const openDir = useCallback(async (dir: string) => {
    try {
      const found = await listFnFiles(dir);
      setProject(dir);
      forgetHistory();
      setConfig(null);
      setConfigSchema(null);
      setView("rules");
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
  }, [forgetHistory]);

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
    if (!project) return true;
    setBusy(true);
    try {
      let decayed: string[] = [];
      if (current && tree && fnDirty) {
        decayed = await writeFn(project, current, tree);
        await load(current, true);
      }
      if (config && configDirty) {
        await configWrite(project, config);
        const again = await configRead(project);
        setConfig(again.values);
        setConfigSaved(JSON.stringify(again.values));
      }
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
  }, [project, current, tree, load, config, fnDirty, configDirty]);
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

  // typing outside an editor goes to the filter: its text is what the user means to enter
  const rulesShown = tree !== null && view === "rules";
  useEffect(() => {
    if (!rulesShown) return;
    const onType = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey || e.isComposing || e.key.length !== 1) return;
      const input = filterInput.current;
      if (!input || question || document.activeElement === input) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], .cm-editor")) return;
      if (e.key === " " && !filterText.trim()) return; // Space on a cell is the cell's
      // before the grid sees it (it would start editing the cell); the character then lands in
      // the field that has just been focused
      e.stopPropagation();
      input.focus();
    };
    window.addEventListener("keydown", onType, true);
    return () => window.removeEventListener("keydown", onType, true);
  }, [rulesShown, question, filterText]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (dirty && !busy) void save();
        return;
      }
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      // inside a text field the field's own undo applies
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      const key = e.key.toLowerCase();
      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (key === "y" || (key === "z" && e.shiftKey)) {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dirty, busy, save, undo, redo]);

  const edit = useCallback((path: string, change: (rule: NonNullable<ReturnType<typeof ruleAt>>) => void, key = "") => {
    remember(treeRef.current, key);
    setTree((old) => {
      if (!old) return old;
      const copy = structuredClone(old);
      const rule = ruleAt(copy, path);
      if (rule) change(rule);
      return copy;
    });
  }, [remember]);

  const editPaths = useCallback(
    (change: (paths: NonNullable<FunctionalFile["paths"]>) => void) => {
      remember(treeRef.current, "paths");
      setTree((old) => {
        if (!old) return old;
        const copy = structuredClone(old);
        change(copy.paths);
        return copy;
      });
    },
    [remember],
  );

  /** Target / Source edits are done by the Python worker (one implementation of the path rules). */
  const remoteEdit = useCallback(
    async (op: "retarget" | "set_source", path: string, value: string) => {
      const current = treeRef.current;
      if (!current) return;
      try {
        const next = await editTree(current, op, path, value);
        remember(current);
        setTree(next);
        setStatus("");
      } catch (e) {
        setStatus(String(e instanceof Error ? e.message : e));
      }
    },
    [remember],
  );

  const openProperties = useCallback(async () => {
    if (!project) return;
    try {
      if (!config) {
        const read = await configRead(project);
        setConfigSchema(read.schema);
        setConfig(read.values);
        setConfigSaved(JSON.stringify(read.values));
      }
      setView("project");
      setStatus("");
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [project, config]);

  // check the draft of mapper.toml as it is edited
  useEffect(() => {
    if (!config) {
      setConfigIssues([]);
      return;
    }
    let stale = false;
    const timer = setTimeout(() => {
      configCheck(config).then(
        (found) => {
          if (!stale) setConfigIssues(found);
        },
        () => {},
      );
    }, 150);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [config]);

  const selectedRow = () => grid.current?.api?.getSelectedRows()[0];

  const addRule = useCallback(async (kind: string, atRoot = false) => {
    const current = treeRef.current;
    if (!current) return;
    const at = atRoot ? { parent: null, index: null } : insertionPoint(selectedRow());
    try {
      const next = await changeStructure(current, { op: "add_rule", ...at, kind });
      remember(current);
      setTree(next);
      if (at.parent) setCollapsed((old) => new Set([...old].filter((p) => p !== at.parent)));
      setStatus("");
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [remember]);

  const deleteRule = useCallback(async (path?: string) => {
    const current = treeRef.current;
    const row = path
      ? flatten(current?.rules ?? []).find((r) => r.path === path)
      : selectedRow();
    if (!current || !row) return;
    const below = descendants(row.rule);
    if (below > 0) {
      const choice = await ask(
        `Delete "${nameOf(row.rule)}" and the ${below} rule${below === 1 ? "" : "s"} inside it?`,
        [
          { id: "delete", label: "Delete", primary: true },
          { id: "cancel", label: "Cancel" },
        ],
      );
      if (choice !== "delete") return;
    }
    try {
      const next = await changeStructure(current, { op: "delete_rule", path: row.path });
      remember(current);
      setTree(next);
      setStatus("");
    } catch (e) {
      setStatus(String(e instanceof Error ? e.message : e));
    }
  }, [ask, remember]);

  const rows = useMemo(
    // lookups have their own view
    () => {
      if (!tree) return [];
      const all = flatten(tree.rules).filter((r) => r.rule.kind !== "lookup");
      // a filter shows what it finds, folded or not
      return filterText.trim() ? filterRows(all, filterText) : visibleRows(all, collapsed);
    },
    [tree, collapsed, filterText],
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
          // same findings: keep the array, or the grid redraws (and closes an open editor)
          if (!stale) setLive((old) => (JSON.stringify(old) === JSON.stringify(found) ? old : found));
        },
        () => {},
      );
    }, 150);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [tree, project, current, python]);

  // what differs from the saved file, per row path ("*" = a new rule)
  const changes = useMemo(() => {
    const found = new Map<string, Set<string>>();
    if (!tree || !saved) return found;
    const before = savedIndex((JSON.parse(saved) as FunctionalFile).rules);
    for (const row of flatten(tree.rules)) {
      const old = row.rule.id
        ? before.byId.get(row.rule.id)
        : (() => {
            const same = before.byPath.get(row.path);
            return same && !same.id ? same : undefined;
          })();
      const cols = changedColumns(row.rule, old);
      if (cols.size) found.set(row.path, cols);
    }
    return found;
  }, [tree, saved]);

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
    const api = grid.current?.api;
    // never under an open editor: redrawing the row would close it
    if (api && api.getEditingCells().length === 0) api.redrawRows();
  }, [diagnostics, changes]);

  // suggestions for the cell being edited: the Python worker knows the schemas and the scope
  const gridContext = useMemo<GridContext>(
    () => ({
      complete: async (path, column, text, cursor) => {
        const now = treeRef.current;
        if (!now || !project || !current || python?.available !== true) {
          return { from: cursor, items: [] };
        }
        const stem = current.replace(/^.*\//, "").replace(/\.fn\.yaml$/, "");
        try {
          return await completeAt(now, project, stem, { path, column, text, cursor });
        } catch {
          return { from: cursor, items: [] };
        }
      },
    }),
    [project, current, python],
  );

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
        cellEditor: CompletingCellEditor,
        valueGetter: (p) => (p.data ? nameOf(p.data.rule) : ""),
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
        editable: editableFor(["field", "loop", "object"]),
        cellEditor: CompletingCellEditor,
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
        cellEditor: CompletingCellEditor,
        // an object that selects an element by its Source has no guard
        editable: (p) =>
          p.data !== undefined &&
          (p.data.rule.kind === "object" ? !p.data.rule.source : ["field", "loop"].includes(p.data.rule.kind)),
        valueGetter: (p) => (p.data ? expressionOf(p.data.rule) : ""),
        // no expression: a field takes its Source value as it is
        cellRenderer: (p: ICellRendererParams<Row>) =>
          !p.value && p.data?.rule.kind === "field" && sourceOf(p.data.rule) ? (
            <span className="muted">= Source value</span>
          ) : (
            p.value
          ),
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
        <button className="history" title="Undo (Ctrl + Z)" disabled={!canUndo || busy} onClick={undo}>
          ↶
        </button>
        <button className="history" title="Redo (Ctrl + Y)" disabled={!canRedo || busy} onClick={redo}>
          ↷
        </button>
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
            onClick={() => void openProperties()}
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
              {f === current && fnDirty ? "*" : ""}
            </div>
          ))}
        </nav>
        <main>
          {(tree || config) && (
            <div className="tabs">
              <button className={view === "rules" ? "tab active" : "tab"} onClick={() => setView("rules")}>
                Rules
              </button>
              <button className={view === "lookups" ? "tab active" : "tab"} onClick={() => setView("lookups")}>
                Lookups
              </button>
              <button className={view === "paths" ? "tab active" : "tab"} onClick={() => setView("paths")}>
                Paths
              </button>
              {config && (
                <button className={view === "project" ? "tab active" : "tab"} onClick={() => setView("project")}>
                  mapper.toml{configDirty ? " ●" : ""}
                </button>
              )}
            </div>
          )}
          {view === "project" && config && configSchema && (
            <ProjectProperties
              schema={configSchema}
              values={config}
              issues={configIssues}
              onChange={(next) => {
                remember(treeRef.current, "config");
                setConfig(next);
              }}
            />
          )}
          {tree && view === "paths" && (
            <Paths
              paths={tree.paths}
              issues={(diagnostics.get("") ?? []).filter((d) => d.message.startsWith("paths:"))}
              onChange={editPaths}
            />
          )}
          {tree && view === "lookups" && (
            <Lookups
              tree={tree}
              diagnostics={diagnostics}
              onEdit={(path, change) =>
                edit(
                  path,
                  (r) => {
                    if (r.kind === "lookup") change(r as LookupRule);
                  },
                  `lookup:${path}`,
                )
              }
              onAdd={() => void addRule("lookup", true)}
              onDelete={(path) => void deleteRule(path)}
            />
          )}
          {tree && view === "rules" && (
            <div className="toolbar">
              <button onClick={() => void addRule("field")}>+ Field</button>
              <button onClick={() => void addRule("object")}>+ Object</button>
              <button onClick={() => void addRule("loop")}>+ Loop</button>
              <button onClick={() => void deleteRule()}>Delete</button>
              <input
                ref={filterInput}
                className="rule-filter"
                type="search"
                placeholder="Filter by rule id or target (customer.name, cusnam)"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && setFilterText("")}
              />
            </div>
          )}
          {tree && view === "rules" ? (
            <div className="grid">
            <AgGridReact<Row>
              rowData={rows}
              columnDefs={columns}
              getRowId={(p) => p.data.path}
              ref={grid}
              tooltipShowDelay={200}
              context={gridContext}
              defaultColDef={{
                sortable: false,
                cellClassRules: {
                  "cell-invalid": (p) => {
                    const cols = invalidColumns(p.data?.path ?? "");
                    return cols.has(p.column.getColId()) || cols.has("*");
                  },
                  "cell-changed": (p) => {
                    const cols = changes.get(p.data?.path ?? "");
                    return !!cols && (cols.has("*") || cols.has(p.column.getColId()));
                  },
                },
              }}
              singleClickEdit
              rowSelection={{ mode: "singleRow", checkboxes: false, enableClickSelection: true }}
              rowClassRules={{
                "row-error": (p) =>
                  (diagnostics.get(p.data?.path ?? "") ?? []).some((d: { severity: string }) => d.severity === "error"),
                "row-warning": (p) =>
                  (diagnostics.get(p.data?.path ?? "") ?? []).some((d: { severity: string }) => d.severity === "warning"),
                "row-review": (p) => (p.data ? reviewState(p.data.rule) === "review" : false),
                "row-validated": (p) => (p.data ? reviewState(p.data.rule) === "validated" : false),
              }}
            />
            </div>
          ) : tree || view === "project" ? null : (
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
        {(diagnostics.get("") ?? [])
          .filter((d) => view !== "paths" || !d.message.startsWith("paths:"))
          .map((d, i) => (
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
