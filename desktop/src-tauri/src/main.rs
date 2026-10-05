// Rust owns the desktop shell (files, subprocesses); Python owns the pipeline
// semantics. Everything here is plumbing to the `mapper` CLI (docs/ARCHITECTURE.md,
// §Desktop tool, §Python runtime).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod bundle;
#[cfg(target_os = "linux")]
mod desktop_entry;
mod input_files;
mod publish_dirs;
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

/// `mapper <command> --json` (build, check, transpile, compile, publish).
///
/// `allow_older`: the user accepted to work on a project whose `mapper.toml` names a newer engine
/// than this one (`--allow-older-engine`); the file is never moved back. `publish` goes to the
/// folder this user chose for the project, if any (`--to`, which beats `[publish] dir`).
#[tauri::command]
fn mapper_command(
    app: tauri::AppHandle,
    project: String,
    command: String,
    allow_older: Option<bool>,
) -> Result<MapperOutput, String> {
    use tauri::Manager;
    if !["build", "check", "transpile", "compile", "publish"].contains(&command.as_str()) {
        return Err(format!("unsupported command: {command}"));
    }
    let mut args: Vec<String> = Vec::new();
    if allow_older == Some(true) {
        args.push("--allow-older-engine".into());
    }
    args.push(command.clone());
    args.push("--json".into());
    if command == "publish" {
        let chosen = app
            .path()
            .app_config_dir()
            .ok()
            .and_then(|dir| publish_dirs::get(dir, &project));
        if let Some(dir) = chosen {
            args.extend(["--to".into(), dir]);
        }
    }
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    run_mapper(&project, &args, None)
}

/// The folder this user publishes `project` to (kept in the app's configuration, not the project).
#[tauri::command]
fn publish_dir_get(app: tauri::AppHandle, project: String) -> Option<String> {
    use tauri::Manager;
    publish_dirs::get(app.path().app_config_dir().ok()?, &project)
}

#[tauri::command]
fn publish_dir_set(
    app: tauri::AppHandle,
    project: String,
    path: Option<String>,
) -> Result<(), String> {
    use tauri::Manager;
    publish_dirs::set(app.path().app_config_dir().map_err(|e| e.to_string())?, &project, path)
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
/// The file `mapping` was last run on in the grid's Output column (kept per user, per project).
#[tauri::command]
fn input_file_get(app: tauri::AppHandle, project: String, mapping: String) -> Option<String> {
    use tauri::Manager;
    input_files::get(app.path().app_config_dir().ok()?, &project, &mapping)
}

#[tauri::command]
fn input_file_set(
    app: tauri::AppHandle,
    project: String,
    mapping: String,
    path: Option<String>,
) -> Result<(), String> {
    use tauri::Manager;
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    input_files::set(dir, &project, &mapping, path)
}

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

/// `J2JME v<version in Cargo.toml> (<short commit id>)`.
fn window_title() -> String {
    format!(
        "J2JME v{} ({})",
        env!("CARGO_PKG_VERSION"),
        env!("J2JME_GIT_SHA")
    )
}

fn main() {
    // `j2jme-desktop --git-helper`: git for the Python side when the `git` binary is not installed
    // (cli/gitops.py): one JSON request on stdin, one answer on stdout, no window
    if std::env::args().nth(1).as_deref() == Some("--git-helper") {
        j2jme_git::helper_main();
    }
    // Wayland takes the window's icon from the .desktop file named like its application id
    #[cfg(target_os = "linux")]
    desktop_entry::match_program_name();
    tour::sweep();
    tauri::Builder::default()
        .manage(EditWorker(Mutex::new(None)))
        .setup(|app| {
            use tauri::Manager;
            if let Ok(dir) = app.path().resource_dir() {
                bundle::set(dir);
            }
            // start the worker in the background so the first edit is already instant
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let state = handle.state::<EditWorker>();
                let _ = ask_worker(&state, r#"{"id":0,"op":"ping"}"#);
            });
            // the window starts hidden: it is sized, then shown
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_title(&window_title());
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
            publish_dir_get,
            publish_dir_set,
            read_fn,
            write_fn,
            edit_request,
            input_file_get,
            input_file_set,
            tour_project_prepare,
            tour_project_cleanup
        ])
        .run(tauri::generate_context!())
        .expect("error while running the desktop tool");
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_title_has_the_cargo_version_and_a_commit_id() {
        let title = super::window_title();
        let rest = title.strip_prefix("J2JME v").expect("prefix");
        let (version, sha) = rest.split_once(" (").expect("version and id");
        assert_eq!(version, env!("CARGO_PKG_VERSION"));
        assert!(sha.ends_with(')') && sha.len() > 1);
    }
}
