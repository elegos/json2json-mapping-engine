//! The JSON file each mapping was last run on (the "blind" input of the grid's Output column).
//! It is a path on this machine, so it lives in the app's configuration folder, per project and
//! mapping, and never in the project (which every user has somewhere else).

use serde_json::{Map, Value};
use std::path::PathBuf;

fn file(dir: PathBuf) -> PathBuf {
    dir.join("input-files.json")
}

fn load(path: &PathBuf) -> Map<String, Value> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .and_then(|v| if let Value::Object(map) = v { Some(map) } else { None })
        .unwrap_or_default()
}

/// The file remembered for `mapping` of `project`, if it is still there.
pub fn get(dir: PathBuf, project: &str, mapping: &str) -> Option<String> {
    let all = load(&file(dir));
    let path = all.get(project)?.get(mapping)?.as_str()?.to_string();
    std::path::Path::new(&path).is_file().then_some(path)
}

/// Remembers `path` for `mapping` of `project`; `None` forgets it.
pub fn set(dir: PathBuf, project: &str, mapping: &str, path: Option<String>) -> Result<(), String> {
    let target = file(dir.clone());
    let mut all = load(&target);
    let mut mappings = match all.remove(project) {
        Some(Value::Object(map)) => map,
        _ => Map::new(),
    };
    match path {
        Some(p) => mappings.insert(mapping.to_string(), Value::String(p)),
        None => mappings.remove(mapping),
    };
    if !mappings.is_empty() {
        all.insert(project.to_string(), Value::Object(mappings));
    }
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let text = serde_json::to_string_pretty(&Value::Object(all)).map_err(|e| e.to_string())?;
    std::fs::write(target, text).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("j2jme-input-files-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    #[test]
    fn remembered_per_project_and_mapping_and_forgotten() {
        let dir = scratch("a");
        let input = dir.join("in.json");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(&input, "{}").unwrap();
        let p = input.display().to_string();
        assert_eq!(get(dir.clone(), "/proj", "orders"), None);
        set(dir.clone(), "/proj", "orders", Some(p.clone())).unwrap();
        assert_eq!(get(dir.clone(), "/proj", "orders"), Some(p));
        assert_eq!(get(dir.clone(), "/proj", "other"), None);
        assert_eq!(get(dir.clone(), "/elsewhere", "orders"), None);
        set(dir.clone(), "/proj", "orders", None).unwrap();
        assert_eq!(get(dir.clone(), "/proj", "orders"), None);
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn a_file_that_is_gone_is_not_offered() {
        let dir = scratch("b");
        set(dir.clone(), "/proj", "orders", Some("/nowhere/in.json".into())).unwrap();
        assert_eq!(get(dir.clone(), "/proj", "orders"), None);
        let _ = std::fs::remove_dir_all(dir);
    }
}
