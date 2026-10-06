//! Drives the real `mapper` CLI through the same code the UI commands use, on the
//! orders fixture. Skipped when no Python with the engine's dependencies is found.

#[path = "../src/bundle.rs"]
#[allow(dead_code)]
mod bundle;

#[path = "../src/python.rs"]
#[allow(dead_code)]
mod python;

#[derive(serde::Serialize)]
pub struct MapperOutput {
    pub json: serde_json::Value,
    pub stdout: String,
    pub stderr: String,
    pub code: i32,
}

fn fixture(name: &str) -> std::path::PathBuf {
    let src = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures/orders-project");
    let dst = std::env::temp_dir().join(format!("j2jme-bridge-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    dst
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap() {
        let e = e.unwrap();
        let to = dst.join(e.file_name());
        if e.file_type().unwrap().is_dir() {
            copy(&e.path(), &to);
        } else {
            std::fs::copy(e.path(), to).unwrap();
        }
    }
}

#[test]
fn read_write_build_round_trip() {
    let Ok(found) = python::resolve() else {
        eprintln!("no usable Python — skipped");
        return;
    };
    let project = fixture("roundtrip");
    let file = "mappings/functional/orders.fn.yaml";

    let read = python::run_mapper(&found, &project, &["fn", "read", file], None, &[]).unwrap();
    assert_eq!(read.code, 0, "{}", read.stderr);
    let mut tree = read.json["file"].clone();
    assert_eq!(tree["id"], "orders");

    tree["rules"][0]["validation"]["validated"] = true.into();
    let body = serde_json::json!({ "file": tree }).to_string();
    let write = python::run_mapper(&found, &project, &["fn", "write", file], Some(&body), &[]).unwrap();
    assert_eq!(write.code, 0, "{}", write.stdout);
    assert_eq!(write.json["ok"], true);

    let build = python::run_mapper(&found, &project, &["build", "--json"], None, &[]).unwrap();
    assert_eq!(build.code, 0, "{}", build.stdout);
    assert_eq!(build.json["ok"], true);
    let _ = std::fs::remove_dir_all(&project);
}

#[test]
fn worker_answers_edits_on_one_process() {
    let Ok(found) = python::resolve() else {
        eprintln!("no usable Python — skipped");
        return;
    };
    let project = fixture("worker");
    let file = "mappings/functional/orders.fn.yaml";
    let read = python::run_mapper(&found, &project, &["fn", "read", file], None, &[]).unwrap();
    let tree = read.json["file"].clone();

    let mut worker = python::Worker::start(&found).unwrap();
    let ping: serde_json::Value =
        serde_json::from_str(&worker.ask(r#"{"id":1,"op":"ping"}"#).unwrap()).unwrap();
    assert_eq!(ping["ok"], true);

    let request = serde_json::json!({
        "id": 2, "op": "retarget", "tree": tree, "path": "rules[2]", "value": "Shipping.Warehouse"
    });
    let answer: serde_json::Value =
        serde_json::from_str(&worker.ask(&request.to_string()).unwrap()).unwrap();
    assert_eq!(answer["ok"], true, "{answer}");
    assert_eq!(answer["id"], 2);
    let rules = answer["tree"]["rules"].as_array().unwrap();
    assert!(rules.iter().any(|r| r["output"] == "$.Shipping"));
    let _ = std::fs::remove_dir_all(&project);
}
