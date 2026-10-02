// Rust owns the desktop shell (files, subprocesses); Python owns the pipeline
// semantics. Everything here is plumbing to the `mapper` CLI (docs/ARCHITECTURE.md,
// §Desktop tool, §Python runtime).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod python;
mod tour;
mod window_size;

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Result of a `mapper` invocation, as the UI needs it.
#[derive(serde::Serialize)]
struct MapperOutput {
    /// Parsed stdout when it is a JSON document, else `null`.
    json: Value,
    stdout: String,
    stderr: String,
    code: i32,
}

#[tauri::command]
fn python_status() -> Value {
    match python::resolve() {
        Ok(found) => serde_json::json!({
            "available": true,
            "python": found.python.display().to_string(),
            "engine": found.engine.display().to_string(),
            "version": found.version,
        }),
        Err(reason) => serde_json::json!({ "available": false, "reason": reason }),
    }
}

/// Project directory given on the command line (`j2jme-desktop <dir>`) or in
/// `J2JME_PROJECT`; the UI opens it at start.
#[tauri::command]
fn initial_project() -> Option<String> {
    std::env::args()
        .nth(1)
        .filter(|a| !a.starts_with('-'))
        .or_else(|| std::env::var("J2JME_PROJECT").ok())
}

/// The `.fn.yaml` files of a project, as paths relative to the project root.
#[tauri::command]
fn list_fn_files(project: String) -> Result<Vec<String>, String> {
    let dir = Path::new(&project).join("mappings").join("functional");
    let entries = fs::read_dir(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    let mut files: Vec<String> = entries
        .filter_map(|e| e.ok())
        .map(|e| e.file_name().to_string_lossy().into_owned())
        .filter(|n| n.ends_with(".fn.yaml"))
        .map(|n| format!("mappings/functional/{n}"))
        .collect();
    files.sort();
    Ok(files)
}

fn run_mapper(project: &str, args: &[&str], stdin: Option<&str>) -> Result<MapperOutput, String> {
    let found = python::resolve()?;
    python::run_mapper(&found, &PathBuf::from(project), args, stdin)
}

/// `mapper <command> --json` (build, check, transpile, compile).
#[tauri::command]
fn mapper_command(project: String, command: String) -> Result<MapperOutput, String> {
    if !["build", "check", "transpile", "compile"].contains(&command.as_str()) {
        return Err(format!("unsupported command: {command}"));
    }
    run_mapper(&project, &[&command, "--json"], None)
}

#[tauri::command]
fn read_fn(project: String, file: String) -> Result<MapperOutput, String> {
    run_mapper(&project, &["fn", "read", &file], None)
}

#[tauri::command]
fn write_fn(project: String, file: String, tree: String) -> Result<MapperOutput, String> {
    run_mapper(&project, &["fn", "write", &file], Some(&tree))
}

/// The edit worker, started on first use (or by `warm_worker`) and restarted if it dies.
struct EditWorker(Mutex<Option<python::Worker>>);

fn ask_worker(state: &EditWorker, request: &str) -> Result<String, String> {
    let mut slot = state
        .0
        .lock()
        .map_err(|_| "worker lock poisoned".to_string())?;
    for _ in 0..2 {
        if slot.is_none() {
            *slot = Some(python::Worker::start(&python::resolve()?)?);
        }
        match slot.as_mut().map(|w| w.ask(request)) {
            Some(Ok(answer)) => return Ok(answer),
            _ => *slot = None, // dead or broken: start a fresh one and retry once
        }
    }
    Err("the edit worker does not answer".into())
}

/// A fresh copy of the tutorial project in a temporary folder; its path.
#[tauri::command]
fn tour_project_prepare() -> Result<String, String> {
    tour::prepare().map(|p| p.display().to_string())
}

/// Deletes a copy made by `tour_project_prepare` (anything else is refused).
#[tauri::command]
fn tour_project_cleanup(path: String) -> Result<(), String> {
    tour::cleanup(Path::new(&path))
}

/// One JSON request to `mapper serve`; returns the JSON answer line.
#[tauri::command]
fn edit_request(state: tauri::State<EditWorker>, request: String) -> Result<String, String> {
    ask_worker(&state, &request)
}

fn main() {
    tour::sweep();
    tauri::Builder::default()
        .manage(EditWorker(Mutex::new(None)))
        .setup(|app| {
            // start the worker in the background so the first edit is already instant
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                use tauri::Manager;
                let state = handle.state::<EditWorker>();
                let _ = ask_worker(&state, r#"{"id":0,"op":"ping"}"#);
            });
            // the window starts hidden: it is sized, then shown
            use tauri::Manager;
            if let Some(window) = app.get_webview_window("main") {
                window_size::setup(&window);
            }
            Ok(())
        })
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            python_status,
            initial_project,
            list_fn_files,
            mapper_command,
            read_fn,
            write_fn,
            edit_request,
            tour_project_prepare,
            tour_project_cleanup
        ])
        .run(tauri::generate_context!())
        .expect("error while running the desktop tool");
}
