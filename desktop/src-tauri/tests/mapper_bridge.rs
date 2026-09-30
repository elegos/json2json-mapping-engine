//! Drives the real `mapper` CLI through the same code the UI commands use, on the
//! orders fixture. Skipped when no Python with the engine's dependencies is found.

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

fn fixture() -> std::path::PathBuf {
    let src = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures/orders-project");
    let dst = std::env::temp_dir().join(format!("j2jme-bridge-{}", std::process::id()));
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
    let project = fixture();
    let file = "mappings/functional/orders.fn.yaml";

    let read = python::run_mapper(&found, &project, &["fn", "read", file], None).unwrap();
    assert_eq!(read.code, 0, "{}", read.stderr);
    let mut tree = read.json["file"].clone();
    assert_eq!(tree["id"], "orders");

    tree["rules"][0]["validation"]["validated"] = true.into();
    let body = serde_json::json!({ "file": tree }).to_string();
    let write = python::run_mapper(&found, &project, &["fn", "write", file], Some(&body)).unwrap();
    assert_eq!(write.code, 0, "{}", write.stdout);
    assert_eq!(write.json["ok"], true);

    let build = python::run_mapper(&found, &project, &["build", "--json"], None).unwrap();
    assert_eq!(build.code, 0, "{}", build.stdout);
    assert_eq!(build.json["ok"], true);
    let _ = std::fs::remove_dir_all(&project);
}
