// A stand-in for the Tauri shell, for taking the guide's screenshots in a browser: the same
// commands the Rust side has (src-tauri/src/main.rs), answered by the real `mapper` CLI and
// `mapper serve`. Not part of the app; used by shots/run.mjs only.
import { execFileSync, spawn } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "../../..");
const python = existsSync(join(root, ".venv/bin/python")) ? join(root, ".venv/bin/python") : "python3";
const env = { ...process.env, PYTHONPATH: root };
export const fixture = join(root, "desktop/fixtures/tour-project");

function runMapper(project, args, stdin) {
  return new Promise((done) => {
    const child = spawn(python, ["-m", "cli.main", ...args], { cwd: project, env });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("close", (code) => {
      let json = null;
      try {
        json = JSON.parse(stdout);
      } catch {
        /* not a JSON document */
      }
      done({ json, stdout, stderr, code: code ?? -1 });
    });
    if (stdin !== undefined) child.stdin.end(stdin);
    else child.stdin.end();
  });
}

// `mapper serve`: one request line in, one answer line out, one at a time
let worker = null;
let queue = Promise.resolve();
function ask(request) {
  const run = () =>
    new Promise((done, fail) => {
      if (!worker) {
        const child = spawn(python, ["-m", "cli.main", "serve"], { env });
        let buffer = "";
        child.stdout.on("data", (d) => {
          buffer += d;
          let at;
          while ((at = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, at);
            buffer = buffer.slice(at + 1);
            child.pending?.shift()?.(line);
          }
        });
        child.pending = [];
        worker = child;
      }
      worker.pending.push(done);
      worker.stdin.write(request.replace(/\n/g, " ") + "\n", (e) => e && fail(e));
    });
  const next = queue.then(run, run);
  queue = next.catch(() => {});
  return next;
}

const copies = [];
let initial = null;

/** The project `initial_project` answers (what the app opens at start). */
export function setInitial(dir) {
  initial = dir;
}

export function makeCopy(name) {
  const dir = name ? join(mkdtempSync(join(tmpdir(), "j2jme-shots-")), name) : mkdtempSync(join(tmpdir(), "j2jme-tour-shots-"));
  cpSync(fixture, dir, { recursive: true });
  // a project outside git gets the "put it under git?" question at open, which covers the shot
  execFileSync("git", ["init", "-q", dir]);
  copies.push(dir);
  return dir;
}

/** What `input_file_set` keeps (the app keeps it in its config folder): "project|mapping" -> path. */
const inputFiles = new Map();
export function setInputFile(project, mapping, path) {
  inputFiles.set(`${project}|${mapping}`, path);
}

const commands = {
  input_file_get: async ({ project, mapping }) => inputFiles.get(`${project}|${mapping}`) ?? null,
  input_file_set: async ({ project, mapping, path }) => {
    if (path) inputFiles.set(`${project}|${mapping}`, path);
    else inputFiles.delete(`${project}|${mapping}`);
  },
  python_status: async () => ({ available: true, python, engine: root, version: "3.12" }),
  initial_project: async () => initial,
  list_fn_files: async ({ project }) =>
    readdirSync(join(project, "mappings/functional"))
      .filter((n) => n.endsWith(".fn.yaml"))
      .sort()
      .map((n) => `mappings/functional/${n}`),
  mapper_command: ({ project, command }) => runMapper(project, [command, "--json"]),
  read_fn: ({ project, file }) => runMapper(project, ["fn", "read", file]),
  write_fn: ({ project, file, tree }) => runMapper(project, ["fn", "write", file], tree),
  edit_request: ({ request }) => ask(request),
  tour_project_prepare: async () => makeCopy(),
  tour_project_cleanup: async ({ path }) => {
    if (copies.includes(path)) rmSync(path, { recursive: true, force: true });
  },
};

export function stop() {
  worker?.kill();
  copies.forEach((d) => rmSync(d, { recursive: true, force: true }));
}

/** Vite plugin: `POST /__bridge/<command>` with the command's arguments as JSON. */
export function bridgePlugin() {
  return {
    name: "j2jme-bridge",
    configureServer(server) {
      server.middlewares.use("/__bridge", (req, res) => {
        let body = "";
        req.on("data", (d) => (body += d));
        req.on("end", async () => {
          const name = (req.url ?? "").replace(/^\//, "").split("?")[0];
          res.setHeader("content-type", "application/json");
          try {
            const run = commands[name];
            if (!run) throw new Error(`unknown command: ${name}`);
            res.end(JSON.stringify({ ok: true, value: await run(body ? JSON.parse(body) : {}) }));
          } catch (e) {
            res.end(JSON.stringify({ ok: false, error: String(e?.message ?? e) }));
          }
        });
      });
    },
  };
}

/** Added to every page before the app runs: `invoke` goes to the bridge. */
export const shim = `
(() => {
  let next = 1;
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
  window.__TAURI_INTERNALS__ = {
    metadata: { currentWindow: { label: "main" }, currentWebview: { label: "main", windowLabel: "main" } },
    transformCallback: () => next++,
    unregisterCallback() {},
    convertFileSrc: (p) => p,
    invoke: async (cmd, args) => {
      if (cmd.startsWith("plugin:")) return 0;
      const r = await (await fetch("/__bridge/" + cmd, { method: "POST", body: JSON.stringify(args ?? {}) })).json();
      if (!r.ok) throw r.error;
      return r.value;
    },
  };
})();
`;
