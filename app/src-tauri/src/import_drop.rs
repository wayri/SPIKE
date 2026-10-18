// SPDX-License-Identifier: Apache-2.0
//! Native user drops grant only the exact existing paths delivered by the OS.
use crate::ApprovedFileState;
use serde::Serialize;
use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{DragDropEvent, Emitter, Manager, Webview, WebviewEvent};

const MAX_DROPPED_PATHS: usize = 32;

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DroppedFile {
    path: String,
    file_name: String,
    is_directory: bool,
}

#[derive(Clone, Debug, Default, Serialize)]
struct ImportDrop {
    files: Vec<DroppedFile>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    rejected: Vec<String>,
}

#[derive(Clone, Serialize)]
struct ImportDrag {
    active: bool,
}

fn approve_dropped_paths(paths: &[PathBuf], approved: &Mutex<HashSet<PathBuf>>) -> ImportDrop {
    let mut result = ImportDrop::default();
    if paths.len() > MAX_DROPPED_PATHS {
        result.rejected.push(format!(
            "Drop at most {MAX_DROPPED_PATHS} files or folders at a time."
        ));
        return result;
    }
    let mut accepted = Vec::new();
    let mut seen = HashSet::new();
    for path in paths {
        let resolved = (|| {
            if !path.is_absolute() {
                return Err("The dropped source must be an absolute local path".to_string());
            }
            let canonical = path.canonicalize().map_err(|error| error.to_string())?;
            let metadata = canonical.metadata().map_err(|error| error.to_string())?;
            if !metadata.is_file() && !metadata.is_dir() {
                return Err("Only regular files and folders can be dropped".to_string());
            }
            let path_text = canonical.to_str().ok_or("The path is not valid Unicode")?;
            let file_name = canonical
                .file_name()
                .and_then(|name| name.to_str())
                .ok_or("The dropped source must have a file or folder name")?;
            let file = DroppedFile {
                path: path_text.to_string(),
                file_name: file_name.to_string(),
                is_directory: metadata.is_dir(),
            };
            Ok((canonical, file))
        })();
        match resolved {
            Ok((canonical, file)) if seen.insert(canonical.clone()) => {
                accepted.push((canonical, file))
            }
            Ok(_) => {}
            Err(error) => result.rejected.push(format!("{}: {error}", path.display())),
        }
    }
    match approved.lock() {
        Ok(mut grants) => {
            for (canonical, file) in accepted {
                grants.insert(canonical);
                result.files.push(file);
            }
        }
        Err(_) => result
            .rejected
            .push("Approved file state is unavailable".to_string()),
    }
    result
}

pub(crate) fn on_webview_event(webview: &Webview, event: &WebviewEvent) {
    if webview.label() != "main" {
        return;
    }
    let WebviewEvent::DragDrop(event) = event else {
        return;
    };
    match event {
        DragDropEvent::Enter { paths, .. } => {
            let _ = webview.emit_to(
                webview.label(),
                "spike://import-drag",
                ImportDrag {
                    active: !paths.is_empty(),
                },
            );
        }
        DragDropEvent::Leave => {
            let _ = webview.emit_to(
                webview.label(),
                "spike://import-drag",
                ImportDrag { active: false },
            );
        }
        DragDropEvent::Drop { paths, .. } => {
            let _ = webview.emit_to(
                webview.label(),
                "spike://import-drag",
                ImportDrag { active: false },
            );
            let paths = paths.clone();
            let webview = webview.clone();
            // Resolving filesystem paths may block; keep it off the native UI loop.
            std::thread::spawn(move || {
                let state = webview.state::<ApprovedFileState>();
                let result = approve_dropped_paths(&paths, &state.0);
                let _ = webview.emit_to(webview.label(), "spike://import-drop", result);
            });
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_ID: AtomicUsize = AtomicUsize::new(0);
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "spike-drop-{}-{}",
                std::process::id(),
                NEXT_ID.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn exact_file_and_directory_grants_do_not_include_children_or_siblings() {
        let fixture = Fixture::new();
        let file = fixture.0.join("board.kicad_pcb");
        fs::write(&file, "fixture").unwrap();
        let directory = fixture.0.join("odb-job");
        fs::create_dir(&directory).unwrap();
        let child = directory.join("matrix");
        fs::write(&child, "fixture").unwrap();
        let sibling = fixture.0.join("private.step");
        fs::write(&sibling, "fixture").unwrap();
        let grants = Mutex::new(HashSet::new());
        let result =
            approve_dropped_paths(&[file.clone(), directory.clone(), file.clone()], &grants);
        assert!(result.rejected.is_empty());
        assert_eq!(result.files.len(), 2);
        assert_eq!(result.files[0].file_name, "board.kicad_pcb");
        assert!(!result.files[0].is_directory);
        assert!(result.files[1].is_directory);
        let grants = grants.lock().unwrap();
        assert_eq!(
            *grants,
            HashSet::from([
                file.canonicalize().unwrap(),
                directory.canonicalize().unwrap()
            ])
        );
        assert!(!grants.contains(&child.canonicalize().unwrap()));
        assert!(!grants.contains(&sibling.canonicalize().unwrap()));
    }

    #[test]
    fn missing_relative_and_url_paths_are_rejected_without_grants() {
        let fixture = Fixture::new();
        let grants = Mutex::new(HashSet::new());
        let result = approve_dropped_paths(
            &[
                fixture.0.join("missing.step"),
                PathBuf::from("relative.step"),
                PathBuf::from("https://example.com/board.step"),
            ],
            &grants,
        );
        assert!(result.files.is_empty());
        assert_eq!(result.rejected.len(), 3);
        assert!(grants.lock().unwrap().is_empty());
    }

    #[test]
    fn oversized_batch_is_rejected_before_any_grants() {
        let fixture = Fixture::new();
        let file = fixture.0.join("board.step");
        fs::write(&file, "fixture").unwrap();
        let grants = Mutex::new(HashSet::new());
        let result = approve_dropped_paths(&vec![file; MAX_DROPPED_PATHS + 1], &grants);
        assert!(result.files.is_empty());
        assert_eq!(result.rejected.len(), 1);
        assert!(grants.lock().unwrap().is_empty());
    }

    #[test]
    fn full_batch_retains_existing_grants_and_reports_mixed_failures() {
        let fixture = Fixture::new();
        let existing = fixture.0.canonicalize().unwrap();
        let grants = Mutex::new(HashSet::from([existing.clone()]));
        let mut paths = Vec::new();
        for index in 0..MAX_DROPPED_PATHS {
            let path = fixture.0.join(format!("model-{index}.step"));
            fs::write(&path, "fixture").unwrap();
            paths.push(path);
        }
        let result = approve_dropped_paths(&paths, &grants);
        assert_eq!(result.files.len(), MAX_DROPPED_PATHS);
        assert!(result.rejected.is_empty());
        assert_eq!(grants.lock().unwrap().len(), MAX_DROPPED_PATHS + 1);
        assert!(grants.lock().unwrap().contains(&existing));
        let result = approve_dropped_paths(&[paths[0].clone(), fixture.0.join("missing")], &grants);
        assert_eq!(result.files.len(), 1);
        assert_eq!(result.rejected.len(), 1);
        let payload = serde_json::to_value(&result).unwrap();
        assert_eq!(payload["files"][0]["fileName"], "model-0.step");
        assert_eq!(payload["files"][0]["isDirectory"], false);
    }
}
