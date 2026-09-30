//! Python resolution and the `mapper` subprocess.
//!
//! Executable resolution order (docs/ARCHITECTURE.md, §Python runtime):
//! 1. `<app-dir>/python-runtime/python` (bundled)
//! 2. `python3.XX` at the minimum version
//! 3. `python3`
//! 4. `python`
//!
//! In a development checkout the engine's own virtualenv comes first, since it is the
//! interpreter that has the engine's dependencies installed. A candidate is accepted
//! only if it can import the engine (`cli.main`).

use crate::MapperOutput;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

/// Minimum Python minor version (`requires-python` in pyproject.toml).
const MIN_MINOR: u32 = 12;

pub struct Found {
    pub python: PathBuf,
    pub engine: PathBuf,
    pub version: String,
}

fn app_dir() -> Option<PathBuf> {
    std::env::current_exe()
        .ok()?
        .parent()
        .map(Path::to_path_buf)
}

/// Where the `cli` / `compiler` / `transpiler` packages live.
fn engine_root() -> Option<PathBuf> {
    if let Ok(dir) = std::env::var("J2JME_ENGINE") {
        return Some(PathBuf::from(dir));
    }
    let bundled = app_dir()?.join("engine");
    if bundled.join("cli").is_dir() {
        return Some(bundled);
    }
    // development checkout: desktop/src-tauri/../..
    let dev = Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..");
    dev.join("cli")
        .is_dir()
        .then(|| dev.canonicalize().unwrap_or(dev))
}

fn candidates(engine: &Path) -> Vec<PathBuf> {
    let mut list = Vec::new();
    if let Some(dir) = app_dir() {
        list.push(dir.join("python-runtime").join("python"));
    }
    list.push(engine.join(".venv").join("bin").join("python"));
    list.push(PathBuf::from(format!("python3.{MIN_MINOR}")));
    list.push(PathBuf::from("python3"));
    list.push(PathBuf::from("python"));
    list
}

fn probe(python: &Path, engine: &Path) -> Option<String> {
    let out = Command::new(python)
        .env("PYTHONPATH", engine)
        .args([
            "-c",
            "import sys, cli.main; print('%d.%d.%d' % sys.version_info[:3])",
        ])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let version = String::from_utf8_lossy(&out.stdout).trim().to_string();
    let minor: u32 = version.split('.').nth(1)?.parse().ok()?;
    (minor >= MIN_MINOR).then_some(version)
}

pub fn resolve() -> Result<Found, String> {
    let engine =
        engine_root().ok_or("engine not found (set J2JME_ENGINE to the directory holding cli/)")?;
    for python in candidates(&engine) {
        if let Some(version) = probe(&python, &engine) {
            return Ok(Found {
                python,
                engine,
                version,
            });
        }
    }
    Err(format!(
        "no usable Python >= 3.{MIN_MINOR} with the engine's dependencies; \
         build actions are disabled"
    ))
}

pub fn run_mapper(
    found: &Found,
    project: &Path,
    args: &[&str],
    stdin: Option<&str>,
) -> Result<MapperOutput, String> {
    let mut child = Command::new(&found.python)
        .current_dir(project)
        .env("PYTHONPATH", &found.engine)
        .args(["-m", "cli.main"])
        .args(args)
        .stdin(if stdin.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("cannot start {}: {e}", found.python.display()))?;
    if let (Some(text), Some(mut pipe)) = (stdin, child.stdin.take()) {
        pipe.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
    }
    let out = child.wait_with_output().map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&out.stdout).into_owned();
    Ok(MapperOutput {
        json: serde_json::from_str(&stdout).unwrap_or(serde_json::Value::Null),
        stdout,
        stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
        code: out.status.code().unwrap_or(-1),
    })
}

/// A long-lived `mapper serve` process: one JSON line in, one JSON line out. Used for
/// the per-edit operations, which must not pay a Python start-up each.
pub struct Worker {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl Worker {
    pub fn start(found: &Found) -> Result<Worker, String> {
        let mut child = Command::new(&found.python)
            .env("PYTHONPATH", &found.engine)
            .args(["-m", "cli.main", "serve"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("cannot start the worker: {e}"))?;
        let stdin = child.stdin.take().ok_or("worker has no stdin")?;
        let stdout = BufReader::new(child.stdout.take().ok_or("worker has no stdout")?);
        Ok(Worker {
            child,
            stdin,
            stdout,
        })
    }

    /// Sends one request line and returns the answer line.
    pub fn ask(&mut self, request: &str) -> Result<String, String> {
        let line = request.replace('\n', " ");
        writeln!(self.stdin, "{line}").map_err(|e| e.to_string())?;
        self.stdin.flush().map_err(|e| e.to_string())?;
        let mut answer = String::new();
        let read = self
            .stdout
            .read_line(&mut answer)
            .map_err(|e| e.to_string())?;
        if read == 0 {
            return Err("the worker stopped".into());
        }
        Ok(answer)
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.child.kill();
    }
}
