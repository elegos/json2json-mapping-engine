use std::process::Command;

/// The short commit id shown in the window title: `J2JME_GIT_SHA` when the build sets it (a
/// container without `.git`), else `git rev-parse --short HEAD`, else `unknown`.
fn git_sha() -> String {
    if let Ok(sha) = std::env::var("J2JME_GIT_SHA") {
        if !sha.trim().is_empty() {
            return sha.trim().to_string();
        }
    }
    Command::new("git")
        .args(["rev-parse", "--short", "HEAD"])
        .output()
        .ok()
        .filter(|out| out.status.success())
        .map(|out| String::from_utf8_lossy(&out.stdout).trim().to_string())
        .filter(|sha| !sha.is_empty())
        .unwrap_or_else(|| "unknown".to_string())
}

fn main() {
    println!("cargo:rustc-env=J2JME_GIT_SHA={}", git_sha());
    println!("cargo:rerun-if-env-changed=J2JME_GIT_SHA");
    println!("cargo:rerun-if-changed=../../.git/HEAD");
    println!("cargo:rerun-if-changed=../../.git/refs/heads");
    tauri_build::build()
}
