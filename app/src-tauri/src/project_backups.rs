// SPDX-License-Identifier: Apache-2.0
//! Native-only recovery location and approved path boundary; Python owns retention.
use serde_json::Value;
use std::path::{Path, PathBuf};

pub fn is_method(method: &str) -> bool {
    matches!(method, "write_project_backup" | "list_project_backups" | "open_project_backup")
}

pub fn prepare(request: &mut Value, root: &Path) -> Result<Vec<PathBuf>, String> {
    let params = request.get_mut("params").and_then(Value::as_object_mut)
        .ok_or("Backup operations require parameter objects")?;
    for key in ["_backup_root", "backup_root", "root", "path", "directory", "project_path", "source_path", "source_paths"] {
        if params.contains_key(key) {
            return Err("Backup paths are controlled by the native host".into());
        }
    }
    let mut paths = Vec::new();
    if let Some(base) = params.get("base_package_path").filter(|v| !v.is_null()) {
        let value = base.as_str().filter(|v| !v.trim().is_empty())
            .ok_or("Backup base package path must be non-empty")?;
        paths.push(std::fs::canonicalize(value).map_err(|e| e.to_string())?);
    }
    params.insert("_backup_root".into(), Value::String(root.to_string_lossy().into_owned()));
    Ok(paths)
}

fn comparable_path(path: &Path) -> Result<PathBuf, String> {
    if let Ok(canonical) = path.canonicalize() { return Ok(canonical); }
    if let (Some(parent), Some(name)) = (path.parent(), path.file_name()) {
        if let Ok(canonical) = parent.canonicalize() { return Ok(canonical.join(name)); }
    }
    let absolute = std::path::absolute(path).map_err(|error| error.to_string())?;
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            std::path::Component::CurDir => {},
            std::path::Component::ParentDir => { normalized.pop(); },
            value => normalized.push(value.as_os_str()),
        }
    }
    Ok(normalized)
}

/// Recovery packages are immutable sources, even after a read grants their path.
pub fn enforce_read_only(request: &Value, root: &Path) -> Result<(), String> {
    let method = request.get("method").and_then(Value::as_str).unwrap_or("");
    if is_method(method) { return Ok(()); } // Only the project route admits these.
    let Some(params) = request.get("params").and_then(Value::as_object) else { return Ok(()); };
    let root = comparable_path(root)?;
    let read_method = matches!(method,
        "read_project_package" | "read_project_model_artifacts"
        | "read_project_package_shape_selector_previews" | "read_project_state_artifact"
        | "read_project_visual_bundle" | "read_assembly_field_study_in_project"
        | "read_volume_electrothermal_in_project" | "read_assembly_thermal_mesh_setup"
        | "prepare_assembly_design_visual_bundle" | "linked_source_status"
        | "load_design" | "import_design_v2" | "list_material_catalog");
    for (key, value) in params {
        if !(key == "path" || key.ends_with("_path") || key.ends_with("_paths")) { continue; }
        let values: Vec<&str> = match value {
            Value::String(text) => vec![text.as_str()],
            Value::Array(items) => items.iter().filter_map(Value::as_str).collect(),
            _ => Vec::new(),
        };
        for path in values {
            if path.is_empty() || !comparable_path(Path::new(path))?.starts_with(&root) { continue; }
            let read_source = read_method && matches!(key.as_str(), "path" | "project_path" | "board_path");
            let save_base = method == "write_project_package" && key == "base_package_path";
            if !read_source && !save_base {
                return Err("Recovery packages are read-only. Save a restored copy outside recovery storage before editing it.".into());
            }
        }
    }
    Ok(())
}

pub fn opened_path(request: &Value, response: &Value, root: &Path) -> Result<Option<PathBuf>, String> {
    if request.get("method").and_then(Value::as_str) != Some("open_project_backup")
        || response.get("ok").and_then(Value::as_bool) != Some(true) {
        return Ok(None);
    }
    let id = request.pointer("/params/id").and_then(Value::as_str)
        .filter(|s| s.len() == 32 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
        .ok_or("Invalid backup identifier")?;
    let expected = root.join(format!("{id}.spike"));
    let canonical = expected.canonicalize().map_err(|e| e.to_string())?;
    let canonical_root = root.canonicalize().map_err(|e| e.to_string())?;
    if canonical.parent() != Some(canonical_root.as_path()) || canonical.file_name() != expected.file_name() {
        return Err("Recovery package escaped its private directory".into());
    }
    let returned = response.pointer("/result/path").and_then(Value::as_str).ok_or("Backup response has no path")?;
    if Path::new(returned).canonicalize().map_err(|e| e.to_string())? != canonical {
        return Err("Recovery package path does not match its identifier".into());
    }
    Ok(Some(canonical))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn approved_recovery_files_remain_read_only_but_can_be_save_bases() {
        let unique = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory = std::env::temp_dir().join(format!("spike-recovery-guard-{unique}"));
        let root = directory.join("recovery");
        std::fs::create_dir_all(&root).unwrap();
        let backup = root.join("approved.spike");
        std::fs::write(&backup, b"already approved for reads").unwrap();
        let outside = directory.join("restored.spike");
        for method in ["write_project_package", "attach_mcad_part_to_project", "update_assembly_structure_in_project", "apply_linked_source_update"] {
            let request = serde_json::json!({"method":method,"params":{"path":backup,"project_path":backup}});
            assert!(enforce_read_only(&request, &root).is_err(), "{method}");
        }
        let new_destination = serde_json::json!({"method":"write_project_package","params":{"path":root.join("new.spike")}});
        assert!(enforce_read_only(&new_destination, &root).is_err());
        for method in ["read_project_package", "read_project_visual_bundle", "read_project_model_artifacts"] {
            let request = serde_json::json!({"method":method,"params":{"path":backup}});
            assert!(enforce_read_only(&request, &root).is_ok());
        }
        let copy = serde_json::json!({"method":"write_project_package","params":{"path":outside,"base_package_path":backup}});
        assert!(enforce_read_only(&copy, &root).is_ok());
        let read_output = serde_json::json!({"method":"read_project_package","params":{"path":backup,"output_path":backup}});
        assert!(enforce_read_only(&read_output, &root).is_err());
        assert_eq!(std::fs::read(&backup).unwrap(), b"already approved for reads");
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn host_injects_private_root_and_rejects_renderer_overrides() {
        let root = std::env::temp_dir().join("spike-backup-boundary");
        for field in ["path", "_backup_root", "root", "project_path", "source_path"] {
            let mut request = serde_json::json!({"method":"write_project_backup","params":{}});
            request["params"][field] = Value::String("untrusted".into());
            assert!(prepare(&mut request, &root).is_err());
        }
        let mut request = serde_json::json!({"method":"list_project_backups","params":{}});
        assert!(prepare(&mut request, &root).unwrap().is_empty());
        assert_eq!(request.pointer("/params/_backup_root").and_then(Value::as_str), root.to_str());
        assert!(is_method("write_project_backup"));
        assert!(!is_method("write_project_package"));
    }
}
