// Rust owns the desktop shell (files, subprocesses); Python owns the pipeline
// semantics. Everything here is plumbing to the `mapper` CLI (docs/ARCHITECTURE.md,
// §Desktop tool, §Python runtime).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod python;

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};

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

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            python_status,
            list_fn_files,
            mapper_command,
            read_fn,
            write_fn
        ])
        .run(tauri::generate_context!())
        .expect("error while running the desktop tool");
}
