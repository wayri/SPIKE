use crate::package_trust::{self, PackageSignatureEnvelope};
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

#[derive(Clone, Debug, PartialEq, Eq)]
struct ProjectManifestBinding {
    manifest_payload_sha256: String,
    authenticated_key_id: Option<String>,
}

pub struct ProjectManifestState(Mutex<HashMap<PathBuf, ProjectManifestBinding>>);

impl ProjectManifestState {
    pub fn new() -> Self {
        Self(Mutex::new(HashMap::new()))
    }
}

pub fn is_targeted_project_read(method: &str) -> bool {
    matches!(
        method,
        "read_project_model_artifacts" | "read_project_package_shape_selector_previews"
            | "read_project_state_artifact" | "read_project_visual_bundle"
            | "export_mcad_session" | "preview_mcad_feedback" | "apply_mcad_feedback"
    )
}

fn valid_manifest_identity(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn request_manifest_identity(request: &Value) -> Result<&str, String> {
    request
        .get("params")
        .and_then(|value| value.get("expected_manifest_payload_sha256"))
        .and_then(Value::as_str)
        .filter(|value| valid_manifest_identity(value))
        .ok_or_else(|| {
            "SPIKE-BE-PACKAGE-S-0001: targeted project read requires an opened manifest identity"
                .to_string()
        })
}

pub fn require_targeted_read_binding(
    method: &str,
    request: &Value,
    project_path: &Path,
    state: &ProjectManifestState,
) -> Result<(), String> {
    if !is_targeted_project_read(method) {
        return Ok(());
    }
    let expected = request_manifest_identity(request)?;
    let bindings = state
        .0
        .lock()
        .map_err(|_| "Project manifest trust state is unavailable".to_string())?;
    let binding = bindings.get(project_path).ok_or_else(|| {
        "SPIKE-BE-PACKAGE-S-0001: open the project through the native host before targeted reads"
            .to_string()
    })?;
    if binding.manifest_payload_sha256 != expected {
        return Err(
            "SPIKE-BE-PACKAGE-S-0002: targeted project read does not match the host-bound manifest identity"
                .to_string(),
        );
    }
    Ok(())
}

fn response_manifest_identity(response: &Value) -> Option<&str> {
    let result = response.get("result")?;
    result
        .get("manifest")
        .and_then(|manifest| manifest.get("manifest_payload_sha256"))
        .or_else(|| result.get("manifest_payload_sha256"))
        .and_then(Value::as_str)
        .filter(|value| valid_manifest_identity(value))
}

fn opened_project_binding(response: &Value) -> Result<ProjectManifestBinding, String> {
    let result = response
        .get("result")
        .ok_or_else(|| "SPIKE-BE-PACKAGE-S-0001: project-open result is missing".to_string())?;
    let identity = response_manifest_identity(response).ok_or_else(|| {
        "SPIKE-BE-PACKAGE-S-0001: project-open manifest identity is missing or malformed"
            .to_string()
    })?;
    let signature_state = result
        .get("manifest_signature")
        .ok_or_else(|| "SPIKE-BE-PACKAGE-S-0001: project signature state is missing".to_string())?;
    if !signature_state
        .get("present")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        return Ok(ProjectManifestBinding {
            manifest_payload_sha256: identity.to_string(),
            authenticated_key_id: None,
        });
    }
    let payload = signature_state
        .get("signed_payload_base64url")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            "SPIKE-BE-PACKAGE-S-0001: signed project is missing canonical verification data"
                .to_string()
        })?;
    let envelope: PackageSignatureEnvelope = serde_json::from_value(
        result
            .get("manifest")
            .and_then(|manifest| manifest.get("signature"))
            .cloned()
            .ok_or_else(|| {
                "SPIKE-BE-PACKAGE-S-0001: signed project is missing its signature envelope"
                    .to_string()
            })?,
    )
    .map_err(|error| {
        format!("SPIKE-BE-PACKAGE-S-0001: project signature envelope is invalid: {error}")
    })?;
    let verified = package_trust::verify_project_manifest(payload, &envelope)?;
    if verified.manifest_payload_sha256 != identity {
        return Err(
            "SPIKE-BE-PACKAGE-S-0002: authenticated project identity does not match the worker-open result"
                .to_string(),
        );
    }
    Ok(ProjectManifestBinding {
        manifest_payload_sha256: identity.to_string(),
        authenticated_key_id: Some(verified.trust.key_id),
    })
}

pub fn update_from_worker_response(
    method: &str,
    project_path: &Path,
    response: &Value,
    state: &ProjectManifestState,
) -> Result<(), String> {
    if response.get("ok").and_then(Value::as_bool) != Some(true) {
        return Ok(());
    }
    if method == "read_project_package"
        && response
            .get("result")
            .and_then(|result| result.get("migrated"))
            .and_then(Value::as_bool)
            == Some(true)
    {
        state
            .0
            .lock()
            .map_err(|_| "Project manifest trust state is unavailable".to_string())?
            .remove(project_path);
        return Ok(());
    }
    let binding = if method == "read_project_package" {
        Some(opened_project_binding(response)?)
    } else {
        response_manifest_identity(response).map(|identity| ProjectManifestBinding {
            manifest_payload_sha256: identity.to_string(),
            authenticated_key_id: None,
        })
    };
    if let Some(binding) = binding {
        state
            .0
            .lock()
            .map_err(|_| "Project manifest trust state is unavailable".to_string())?
            .insert(project_path.to_path_buf(), binding);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn saved_results_and_visuals_require_native_open_identity() {
        for method in ["read_project_state_artifact", "read_project_visual_bundle"] {
            assert!(is_targeted_project_read(method));
            let state = ProjectManifestState::new();
            let path = PathBuf::from("saved.spike");
            let request = json!({"params": {"expected_manifest_payload_sha256": "a".repeat(64)}});
            assert!(require_targeted_read_binding(method, &request, &path, &state).is_err());
            let response = json!({"ok": true, "result": {"manifest": {"manifest_payload_sha256": "a".repeat(64)}, "manifest_signature": {"present": false}, "migrated": false}});
            update_from_worker_response("read_project_package", &path, &response, &state).unwrap();
            require_targeted_read_binding(method, &request, &path, &state).unwrap();
            let stale = json!({"params": {"expected_manifest_payload_sha256": "b".repeat(64)}});
            assert!(require_targeted_read_binding(method, &stale, &path, &state).is_err());
        }
    }

    #[test]
    fn unsigned_open_binds_identity_and_targeted_reads_require_exact_match() {
        let state = ProjectManifestState::new();
        let path = PathBuf::from("fixture.spike");
        let identity = "a".repeat(64);
        let response = json!({
            "ok": true,
            "result": {
                "manifest": {"manifest_payload_sha256": identity},
                "manifest_signature": {"present": false},
                "migrated": false
            }
        });
        update_from_worker_response("read_project_package", &path, &response, &state).unwrap();
        let request = json!({
            "params": {"expected_manifest_payload_sha256": "a".repeat(64)}
        });
        require_targeted_read_binding(
            "read_project_model_artifacts", &request, &path, &state,
        )
        .unwrap();
        let stale = json!({
            "params": {"expected_manifest_payload_sha256": "b".repeat(64)}
        });
        assert!(require_targeted_read_binding(
            "read_project_model_artifacts", &stale, &path, &state,
        )
        .unwrap_err()
        .contains("host-bound"));
    }

    #[test]
    fn targeted_read_before_native_open_is_rejected() {
        let request = json!({
            "params": {"expected_manifest_payload_sha256": "a".repeat(64)}
        });
        let error = require_targeted_read_binding(
            "read_project_package_shape_selector_previews",
            &request,
            Path::new("unopened.spike"),
            &ProjectManifestState::new(),
        )
        .unwrap_err();
        assert!(error.contains("open the project"));
    }

    #[test]
    fn successful_mutation_advances_binding_as_unsigned_identity() {
        let state = ProjectManifestState::new();
        let path = PathBuf::from("fixture.spike");
        let response = json!({
            "ok": true,
            "result": {"manifest": {"manifest_payload_sha256": "c".repeat(64)}}
        });
        update_from_worker_response("update_mcad_part_in_project", &path, &response, &state)
            .unwrap();
        let request = json!({
            "params": {"expected_manifest_payload_sha256": "c".repeat(64)}
        });
        require_targeted_read_binding(
            "read_project_model_artifacts", &request, &path, &state,
        )
        .unwrap();
    }
}
