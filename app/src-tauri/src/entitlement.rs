use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use chrono::{DateTime, Utc};
use ed25519_dalek::{Signature, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::PathBuf;
use tauri::Manager;

const ENTITLEMENT_FILE: &str = "license-entitlement-v1.json";
const PRODUCT: &str = "SPIKE";
const PRODUCT_MAJOR: u32 = 0;

fn expected_key_id() -> &'static str {
    option_env!("SPIKE_LICENSE_KEY_ID").unwrap_or("spike-license-root-v1")
}

/// Development issuer root public key (a public value, not a secret). It is a
/// compile-time fallback so the issuer key is embedded regardless of whether
/// Cargo's `[env]` table is discovered from the build's working directory
/// (config discovery is CWD-relative and can be missed by npm/tauri builds).
/// Release engineering overrides it by compiling with
/// `SPIKE_LICENSE_PUBLIC_KEY_B64URL` set to the production issuer key.
const DEV_PUBLIC_KEY_B64URL: &str = "yka23m8hOVS4-AVLMNtMrlpKUMmL0THT7qW5_V3HjtE";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct LicenseEnvelope {
    schema: String,
    key_id: String,
    payload_base64url: String,
    signature_base64url: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct LicenseClaims {
    schema: String,
    license_id: String,
    activation_id: String,
    subject_id: String,
    subject_name: String,
    tier: String,
    license_type: String,
    capabilities: Vec<String>,
    product: String,
    product_major: u32,
    issued_at: String,
    not_before: String,
    expires_at: Option<String>,
    refresh_after: Option<String>,
    device_public_key_sha256: String,
    revocation_epoch: u64,
    organization_id: Option<String>,
    offline: bool,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LicenseSummary {
    pub tier: String,
    pub status: String,
    pub licensee: String,
    pub source: String,
    pub expires_at: Option<String>,
    pub capabilities: Vec<String>,
    pub license_id: Option<String>,
    pub license_type: Option<String>,
    pub device_binding: String,
    pub error_code: Option<String>,
    pub message: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DeviceBindingSummary {
    pub schema: &'static str,
    pub device_public_key_sha256: String,
    pub product: &'static str,
    pub product_major: u32,
}

/// Every capability the product can ever gate. Used for display and for the
/// debug-only development unlock; enforcement stays deny-by-default per
/// capability in production.
#[cfg_attr(not(debug_assertions), allow(dead_code))]
pub const ALL_CAPABILITIES: [&str; 16] = [
    "project.read",
    "project.write",
    "design.import",
    "pi.dc",
    "pi.ac",
    "pi.transient",
    "spice.execute",
    "thermal.prepare",
    "thermal.solve",
    "si.solve",
    "emi.solve",
    "report.export",
    "step.export",
    "validation.run",
    "solver.extensions",
    "administration.settings",
];

impl LicenseSummary {
    #[cfg_attr(debug_assertions, allow(dead_code))]
    fn unlicensed(binding: String, code: &str, message: impl Into<String>) -> Self {
        Self {
            tier: "evaluation".to_string(),
            status: "unlicensed".to_string(),
            licensee: "Unlicensed user".to_string(),
            source: "none".to_string(),
            expires_at: None,
            capabilities: vec!["project.read".to_string()],
            license_id: None,
            license_type: None,
            device_binding: binding,
            error_code: Some(code.to_string()),
            message: Some(message.into()),
        }
    }

    /// Debug-build development unlock required by docs/LICENSE_ENGINE_ARCHITECTURE.md:
    /// clearly displayed, all capabilities enabled locally, and compiled out of
    /// release builds so it can never ship or be re-enabled through packaging.
    #[cfg(debug_assertions)]
    fn development(binding: String) -> Self {
        Self {
            tier: "developer".to_string(),
            status: "active".to_string(),
            licensee: "Local developer (development build)".to_string(),
            source: "development-build".to_string(),
            expires_at: None,
            capabilities: ALL_CAPABILITIES
                .iter()
                .map(|capability| capability.to_string())
                .collect(),
            license_id: Some("SPIKE-DEV-BUILD-LOCAL".to_string()),
            license_type: Some("developer".to_string()),
            device_binding: binding,
            error_code: None,
            message: Some(
                "Development build unlock: every capability is enabled on this machine. \
                 This bypass exists only in debug builds and is absent from release \
                 binaries; signed licenses still take precedence when installed."
                    .to_string(),
            ),
        }
    }

    pub fn permits(&self, capability: &str) -> bool {
        self.status == "active"
            && (self.tier == "developer"
                || self.license_type.as_deref() == Some("developer")
                || self.capabilities.iter().any(|item| item == capability))
    }
}

fn parse_time(value: &str, field: &str) -> Result<DateTime<Utc>, String> {
    DateTime::parse_from_rfc3339(value)
        .map(|parsed| parsed.with_timezone(&Utc))
        .map_err(|_| format!("SPIKE-BE-SECURITY-E-0001: {field} must be an RFC 3339 timestamp"))
}

fn machine_identity() -> String {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        let output = std::process::Command::new("reg.exe")
            .args([
                "query",
                r"HKLM\SOFTWARE\Microsoft\Cryptography",
                "/v",
                "MachineGuid",
            ])
            .creation_flags(0x08000000)
            .output()
            .ok();
        if let Some(output) = output.filter(|value| value.status.success()) {
            let text = String::from_utf8_lossy(&output.stdout);
            if let Some(value) = text
                .lines()
                .find(|line| line.contains("MachineGuid"))
                .and_then(|line| line.split_whitespace().last())
            {
                return value.to_string();
            }
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"] {
            if let Ok(value) = fs::read_to_string(path) {
                let value = value.trim();
                if !value.is_empty() {
                    return value.to_string();
                }
            }
        }
    }
    "unavailable-machine-id".to_string()
}

pub fn device_binding() -> String {
    let user = std::env::var("USERNAME")
        .or_else(|_| std::env::var("USER"))
        .unwrap_or_else(|_| "unavailable-user-id".to_string());
    let domain = std::env::var("USERDOMAIN").unwrap_or_default();
    let mut digest = Sha256::new();
    digest.update(b"spike-device-user-binding-v1\0");
    digest.update(machine_identity().as_bytes());
    digest.update(b"\0");
    digest.update(domain.as_bytes());
    digest.update(b"\\");
    digest.update(user.as_bytes());
    hex::encode(digest.finalize())
}

fn entitlement_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_local_data_dir()
        .map(|path| path.join(ENTITLEMENT_FILE))
        .map_err(|error| {
            format!("SPIKE-BE-SECURITY-E-0004: license storage is unavailable: {error}")
        })
}

fn verifying_key() -> Result<VerifyingKey, String> {
    let encoded = option_env!("SPIKE_LICENSE_PUBLIC_KEY_B64URL")
        .unwrap_or(DEV_PUBLIC_KEY_B64URL);
    let bytes = URL_SAFE_NO_PAD.decode(encoded).map_err(|_| {
        "SPIKE-BE-SECURITY-S-0001: the pinned license issuer key is malformed".to_string()
    })?;
    let bytes: [u8; 32] = bytes.try_into().map_err(|_| {
        "SPIKE-BE-SECURITY-S-0001: the pinned license issuer key must be 32 bytes".to_string()
    })?;
    VerifyingKey::from_bytes(&bytes).map_err(|_| {
        "SPIKE-BE-SECURITY-S-0001: the pinned license issuer key is invalid".to_string()
    })
}

fn verify_with_key(
    contents: &str,
    key: &VerifyingKey,
    binding: &str,
) -> Result<LicenseSummary, String> {
    let envelope: LicenseEnvelope = serde_json::from_str(contents)
        .map_err(|error| format!("SPIKE-BE-SECURITY-S-0002: invalid license envelope: {error}"))?;
    if envelope.schema != "spike/license-entitlement/v1" || envelope.key_id != expected_key_id() {
        return Err("SPIKE-BE-SECURITY-S-0002: unsupported license envelope".to_string());
    }
    let payload = URL_SAFE_NO_PAD
        .decode(&envelope.payload_base64url)
        .map_err(|_| {
            "SPIKE-BE-SECURITY-S-0002: license payload is not valid base64url".to_string()
        })?;
    let signature = URL_SAFE_NO_PAD
        .decode(&envelope.signature_base64url)
        .map_err(|_| {
            "SPIKE-BE-SECURITY-S-0002: license signature is not valid base64url".to_string()
        })?;
    let signature = Signature::from_slice(&signature).map_err(|_| {
        "SPIKE-BE-SECURITY-S-0003: license signature has the wrong length".to_string()
    })?;
    key.verify_strict(&payload, &signature).map_err(|_| {
        "SPIKE-BE-SECURITY-S-0003: license signature verification failed".to_string()
    })?;
    let claims: LicenseClaims = serde_json::from_slice(&payload)
        .map_err(|error| format!("SPIKE-BE-SECURITY-E-0001: invalid license claims: {error}"))?;

    if claims.schema != "spike/license-claims/v1"
        || claims.product != PRODUCT
        || claims.product_major != PRODUCT_MAJOR
    {
        return Err(
            "SPIKE-BE-SECURITY-E-0002: license is for a different product or major version"
                .to_string(),
        );
    }
    if claims.device_public_key_sha256 != binding {
        return Err(
            "SPIKE-BE-SECURITY-S-0004: license is bound to a different machine or user".to_string(),
        );
    }
    if claims.license_id.trim().is_empty()
        || claims.activation_id.trim().is_empty()
        || claims.subject_id.trim().is_empty()
        || claims.capabilities.is_empty()
    {
        return Err("SPIKE-BE-SECURITY-E-0001: required license claims are empty".to_string());
    }
    if !matches!(
        claims.tier.as_str(),
        "evaluation" | "professional" | "enterprise" | "developer"
    ) {
        return Err("SPIKE-BE-SECURITY-E-0001: unsupported license tier".to_string());
    }
    if !matches!(
        claims.license_type.as_str(),
        "temporary" | "timed" | "perpetual" | "developer"
    ) {
        return Err("SPIKE-BE-SECURITY-E-0001: unsupported license type".to_string());
    }
    if claims.license_type == "developer" && claims.tier != "developer" {
        return Err(
            "SPIKE-BE-SECURITY-E-0001: developer licenses require the developer tier".to_string(),
        );
    }
    let now = Utc::now();
    let issued_at = parse_time(&claims.issued_at, "issued_at")?;
    let not_before = parse_time(&claims.not_before, "not_before")?;
    if issued_at > now + chrono::Duration::minutes(5) || not_before > now {
        return Err("SPIKE-BE-SECURITY-E-0003: license is not yet valid".to_string());
    }
    let expires_at = claims
        .expires_at
        .as_deref()
        .map(|value| parse_time(value, "expires_at"))
        .transpose()?;
    if matches!(
        claims.license_type.as_str(),
        "temporary" | "timed" | "developer"
    ) && expires_at.is_none()
    {
        return Err(
            "SPIKE-BE-SECURITY-E-0001: temporary, timed, and developer licenses require expires_at"
                .to_string(),
        );
    }
    if expires_at.is_some_and(|value| value <= now) {
        return Err("SPIKE-BE-SECURITY-E-0003: license has expired".to_string());
    }
    if let Some(refresh_after) = claims.refresh_after.as_deref() {
        let _ = parse_time(refresh_after, "refresh_after")?;
    }
    let _audited_claims = (
        claims.activation_id,
        claims.subject_id,
        claims.revocation_epoch,
        claims.organization_id,
        claims.offline,
    );
    Ok(LicenseSummary {
        tier: claims.tier,
        status: "active".to_string(),
        licensee: claims.subject_name,
        source: "signed-license".to_string(),
        expires_at: claims.expires_at,
        capabilities: claims.capabilities,
        license_id: Some(claims.license_id),
        license_type: Some(claims.license_type),
        device_binding: binding.to_string(),
        error_code: None,
        message: None,
    })
}

fn verify(contents: &str, binding: &str) -> Result<LicenseSummary, String> {
    verify_with_key(contents, &verifying_key()?, binding)
}

/// Deny protected work, or — in debug builds only — return the clearly
/// displayed development unlock. Release builds never compile the unlock.
fn denied(binding: String, code: &str, message: impl Into<String>) -> LicenseSummary {
    #[cfg(debug_assertions)]
    {
        let _ = (&code, &message);
        LicenseSummary::development(binding)
    }

    #[cfg(not(debug_assertions))]
    {
        let _ = code;
        LicenseSummary::unlicensed(binding, code, message)
    }
}

pub fn status(app: &tauri::AppHandle) -> LicenseSummary {
    let binding = device_binding();
    let path = match entitlement_path(app) {
        Ok(path) => path,
        Err(error) => return denied(binding, "SPIKE-BE-SECURITY-E-0004", error),
    };
    let contents = match fs::read_to_string(path) {
        Ok(contents) => contents,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return denied(
                binding,
                "SPIKE-BE-SECURITY-E-0005",
                "No license is installed",
            )
        }
        Err(error) => return denied(binding, "SPIKE-BE-SECURITY-E-0004", error.to_string()),
    };
    match verify(&contents, &binding) {
        Ok(summary) => summary,
        Err(error) => {
            let code = error
                .split(':')
                .next()
                .unwrap_or("SPIKE-BE-SECURITY-S-0002");
            let mut summary = denied(binding, code, &error);
            if !cfg!(debug_assertions) {
                if code == "SPIKE-BE-SECURITY-E-0003" && error.contains("expired") {
                    summary.status = "expired".to_string();
                } else if code != "SPIKE-BE-SECURITY-E-0005" {
                    summary.status = "invalid".to_string();
                }
            }
            summary
        }
    }
}

pub fn activate(app: &tauri::AppHandle, contents: &str) -> Result<LicenseSummary, String> {
    if contents.len() > 128 * 1024 {
        return Err("SPIKE-BE-SECURITY-S-0002: license envelope exceeds 128 KiB".to_string());
    }
    let binding = device_binding();
    let summary = verify(contents, &binding)?;
    let path = entitlement_path(app)?;
    let parent = path
        .parent()
        .ok_or("SPIKE-BE-SECURITY-E-0004: invalid license storage path")?;
    fs::create_dir_all(parent).map_err(|error| {
        format!("SPIKE-BE-SECURITY-E-0004: cannot create license storage: {error}")
    })?;
    let temporary = path.with_extension("json.tmp");
    fs::write(&temporary, contents.as_bytes())
        .map_err(|error| format!("SPIKE-BE-SECURITY-E-0004: cannot write license: {error}"))?;
    let backup = path.with_extension("json.bak");
    if path.exists() {
        let _ = fs::remove_file(&backup);
        fs::rename(&path, &backup).map_err(|error| {
            format!("SPIKE-BE-SECURITY-E-0004: cannot stage the current license: {error}")
        })?;
    }
    if let Err(error) = fs::rename(&temporary, &path) {
        let _ = fs::rename(&backup, &path);
        return Err(format!(
            "SPIKE-BE-SECURITY-E-0004: cannot activate license atomically: {error}"
        ));
    }
    let _ = fs::remove_file(backup);
    Ok(summary)
}

pub fn deactivate(app: &tauri::AppHandle) -> Result<LicenseSummary, String> {
    let path = entitlement_path(app)?;
    match fs::remove_file(path) {
        Ok(()) => Ok(status(app)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(status(app)),
        Err(error) => Err(format!(
            "SPIKE-BE-SECURITY-E-0004: cannot remove license: {error}"
        )),
    }
}

/// Return the raw installed entitlement envelope so the interface can export
/// the signed license to a file the user keeps as a portable backup and
/// re-uploads at any time to restore access on the same machine/user. The
/// signed payload is public material (key_id, claims, signature); it is not a
/// secret and never contains private keys.
pub fn export(app: &tauri::AppHandle) -> Result<String, String> {
    let path = entitlement_path(app)?;
    let contents = fs::read_to_string(&path).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            "SPIKE-BE-SECURITY-E-0005: No license is installed to export".to_string()
        } else {
            format!("SPIKE-BE-SECURITY-E-0004: cannot read license: {error}")
        }
    })?;
    // Re-verify before handing the entitlement back so a corrupt/foreign
    // installed file cannot be propagated as a portable backup.
    let _ = verify(&contents, &device_binding())?;
    if contents.len() > 128 * 1024 {
        return Err("SPIKE-BE-SECURITY-S-0002: license envelope exceeds 128 KiB".to_string());
    }
    Ok(contents)
}

pub fn device_request() -> DeviceBindingSummary {
    DeviceBindingSummary {
        schema: "spike/license-device-request/v1",
        device_public_key_sha256: device_binding(),
        product: PRODUCT,
        product_major: PRODUCT_MAJOR,
    }
}

pub fn capability_for_worker(request: &serde_json::Value) -> &'static str {
    match request
        .get("method")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
    {
        "run_si_uniform_channel" | "run_si_protocol_test_suite" | "run_si_workflow" => "si.solve",
        "run_harness_pi" => "pi.dc",
        "generate_tetrahedral_mesh" => "pi.dc",
        "run_spice_workspace_native_mna"
        | "run_owned_spice_workspace"
        | "run_converter_study"
        | "run_field_circuit_cosimulation" => "spice.execute",
        "prepare_thermal_case" | "run_thermal_case" => "thermal.prepare",
        "extract_mcad_package_shape_in_project" | "generate_mcad_selector_preview_in_project" | "update_assembly_topology_setup_in_project" | "apply_assembly_geometric_constraint_in_project" | "update_assembly_structure_in_project" | "import_into_assembly_project" => "project.write",
        "apply_mcad_feedback" => "project.write",
        "export_step" => "step.export",
        "benchmarks" => "validation.run",
        "prepare_openems_case"
        | "run_openems_case"
        | "prepare_sparselizard_case"
        | "run_sparselizard_case"
        | "discover_extensions"
        | "invoke_extension" => "solver.extensions",
        "preview_mesh" | "mesh_convergence" | "prepare_3d_scene" | "prepare_visual_bundle" => {
            "pi.dc"
        }
        "run_analysis" | "run_preflighted_analysis" => {
            let mode = request
                .pointer("/params/spec/analysis_type")
                .or_else(|| request.pointer("/params/spec/mode"))
                .or_else(|| request.pointer("/params/analysis_type"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_ascii_lowercase();
            if mode.contains("transient") {
                "pi.transient"
            } else if mode.contains("si") || mode.contains("signal") {
                "si.solve"
            } else if mode.contains("ac") || mode.contains("impedance") {
                "pi.ac"
            } else {
                "pi.dc"
            }
        }
        _ => "project.read",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};
    use serde_json::json;

    fn signed_entitlement(binding: &str, expires_at: Option<&str>) -> (String, VerifyingKey) {
        let signing = SigningKey::from_bytes(&[7_u8; 32]);
        let payload = serde_json::to_vec(&json!({
            "schema": "spike/license-claims/v1",
            "license_id": "lic-test",
            "activation_id": "act-test",
            "subject_id": "user-test",
            "subject_name": "Test Engineer",
            "tier": "developer",
            "license_type": "developer",
            "capabilities": ["project.read", "pi.dc"],
            "product": "SPIKE",
            "product_major": 0,
            "issued_at": "2025-01-01T00:00:00Z",
            "not_before": "2025-01-01T00:00:00Z",
            "expires_at": expires_at,
            "refresh_after": null,
            "device_public_key_sha256": binding,
            "revocation_epoch": 0,
            "organization_id": null,
            "offline": true
        }))
        .unwrap();
        let signature = signing.sign(&payload);
        let envelope = json!({
            "schema": "spike/license-entitlement/v1",
            "key_id": "spike-license-root-v1",
            "payload_base64url": URL_SAFE_NO_PAD.encode(&payload),
            "signature_base64url": URL_SAFE_NO_PAD.encode(signature.to_bytes())
        });
        (
            serde_json::to_string(&envelope).unwrap(),
            signing.verifying_key(),
        )
    }

    #[test]
    fn accepts_signed_device_bound_developer_license() {
        let (entitlement, key) = signed_entitlement("binding-a", Some("2099-01-01T00:00:00Z"));
        let summary = verify_with_key(&entitlement, &key, "binding-a").unwrap();
        assert!(summary.permits("pi.dc"));
        assert!(summary.permits("solver.extensions"));
        assert_eq!(summary.license_type.as_deref(), Some("developer"));
    }

    #[test]
    fn rejects_license_copied_to_another_device_or_user() {
        let (entitlement, key) = signed_entitlement("binding-a", Some("2099-01-01T00:00:00Z"));
        let error = verify_with_key(&entitlement, &key, "binding-b").unwrap_err();
        assert!(error.starts_with("SPIKE-BE-SECURITY-S-0004"));
    }

    #[test]
    fn rejects_developer_license_without_expiry() {
        let (entitlement, key) = signed_entitlement("binding-a", None);
        let error = verify_with_key(&entitlement, &key, "binding-a").unwrap_err();
        assert!(error.contains("developer licenses require expires_at"));
    }

    #[test]
    fn rejects_tampered_payload() {
        let (entitlement, key) = signed_entitlement("binding-a", Some("2099-01-01T00:00:00Z"));
        let tampered = entitlement.replace("spike-license-root-v1", "spike-license-root-v2");
        let error = verify_with_key(&tampered, &key, "binding-a").unwrap_err();
        assert!(error.starts_with("SPIKE-BE-SECURITY-S-0002"));
        let mut value: serde_json::Value = serde_json::from_str(&entitlement).unwrap();
        value["payload_base64url"] = json!(URL_SAFE_NO_PAD.encode(b"{}"));
        let error = verify_with_key(&value.to_string(), &key, "binding-a").unwrap_err();
        assert!(error.starts_with("SPIKE-BE-SECURITY-S-0003"));
    }

    #[cfg(debug_assertions)]
    #[test]
    fn debug_denial_unlocks_every_capability_and_is_clearly_labeled() {
        let summary = denied(
            "binding-dev".to_string(),
            "SPIKE-BE-SECURITY-E-0005",
            "No license is installed",
        );
        assert_eq!(summary.status, "active");
        assert_eq!(summary.tier, "developer");
        assert_eq!(summary.source, "development-build");
        assert_eq!(summary.license_type.as_deref(), Some("developer"));
        assert!(
            summary.message.as_deref().unwrap_or_default().contains("Development build unlock"),
            "the unlock must be clearly displayed"
        );
        for capability in ALL_CAPABILITIES {
            assert!(summary.permits(capability), "{capability} must be unlocked");
        }
    }

    #[test]
    fn development_unlock_covers_every_worker_capability() {
        let requests = [
            json!({"method": "run_analysis", "params": {"spec": {"analysis_type": "dc"}}}),
            json!({"method": "run_analysis", "params": {"spec": {"analysis_type": "ac_impedance"}}}),
            json!({"method": "run_analysis", "params": {"spec": {"analysis_type": "transient"}}}),
            json!({"method": "run_spice_workspace_native_mna"}),
            json!({"method": "run_owned_spice_workspace"}),
            json!({"method": "run_converter_study"}),
            json!({"method": "run_field_circuit_cosimulation"}),
            json!({"method": "prepare_thermal_case"}),
            json!({"method": "run_thermal_case"}),
            json!({"method": "export_step"}),
            json!({"method": "benchmarks"}),
            json!({"method": "prepare_openems_case"}),
            json!({"method": "run_openems_case"}),
            json!({"method": "prepare_sparselizard_case"}),
            json!({"method": "run_sparselizard_case"}),
            json!({"method": "discover_extensions"}),
            json!({"method": "invoke_extension"}),
            json!({"method": "validate_si_protocol_suite"}),
            json!({"method": "plan_si_protocol_analysis"}),
            json!({"method": "run_si_uniform_channel"}),
            json!({"method": "run_analysis", "params": {"spec": {"analysis_type": "si"}}}),
            json!({"method": "preview_mesh"}),
            json!({"method": "mesh_convergence"}),
            json!({"method": "prepare_3d_scene"}),
            json!({"method": "prepare_visual_bundle"}),
            json!({"method": "extract_mcad_package_shape_in_project"}),
            json!({"method": "generate_mcad_selector_preview_in_project"}),
            json!({"method": "update_assembly_topology_setup_in_project"}),
            json!({"method": "apply_assembly_geometric_constraint_in_project"}),
            json!({"method": "update_assembly_structure_in_project"}),
            json!({"method": "something_not_yet_mapped"}),
        ];
        // In debug builds the denial path is the development unlock and must
        // cover every capability the host can request. In release builds this
        // test still asserts the deny-by-default contract: the unlicensed
        // summary grants nothing. The host separately admits project.read
        // before consulting LicenseSummary::permits.
        let summary = denied(
            "binding-worker".to_string(),
            "SPIKE-BE-SECURITY-E-0005",
            "No license is installed",
        );
        for request in requests {
            let capability = capability_for_worker(&request);
            if cfg!(debug_assertions) {
                assert!(summary.permits(capability), "{capability} must be unlocked");
            } else {
                assert!(
                    !summary.permits(capability),
                    "{capability} must stay deny-by-default in the release license summary"
                );
            }
        }
    }

    #[test]
    fn pinned_public_key_constant_is_embedded_and_well_formed() {
        let bytes = URL_SAFE_NO_PAD
            .decode(DEV_PUBLIC_KEY_B64URL)
            .expect("embedded dev public key must be valid base64url");
        let bytes: [u8; 32] = bytes
            .as_slice()
            .try_into()
            .expect("embedded dev public key must be 32 bytes");
        let key = VerifyingKey::from_bytes(&bytes)
            .expect("embedded dev public key must be a valid Ed25519 key");
        assert_eq!(key.to_bytes(), bytes);
        // The build-time env override wins when present; otherwise the constant
        // must resolve so release builds are never left with no issuer key.
        let encoded = option_env!("SPIKE_LICENSE_PUBLIC_KEY_B64URL")
            .unwrap_or(DEV_PUBLIC_KEY_B64URL);
        let configured_bytes = URL_SAFE_NO_PAD
            .decode(encoded)
            .expect("configured issuer key must be valid base64url");
        let configured_bytes: [u8; 32] = configured_bytes
            .as_slice()
            .try_into()
            .expect("configured issuer key must be 32 bytes");
        assert_eq!(
            verifying_key().expect("configured issuer key must be valid Ed25519").to_bytes(),
            configured_bytes,
            "runtime verification must use the configured build-time key",
        );
    }

    #[test]
    fn exported_entitlement_is_portable_and_reactivatable() {
        // A saved license file is exactly the signed envelope, so re-uploading
        // it must re-verify on the same machine/user binding. This exercises the
        // round-trip the interface uses for "Save license file" then
        // "Load license file".
        let (entitlement, key) = signed_entitlement("binding-a", Some("2099-01-01T00:00:00Z"));
        let exported = entitlement.as_bytes();
        let summary = verify_with_key(
            std::str::from_utf8(exported).unwrap(),
            &key,
            "binding-a",
        )
        .expect("exported entitlement must re-verify");
        assert_eq!(summary.status, "active");
        // A foreign machine/user binding must still be rejected after export.
        let error = verify_with_key(
            std::str::from_utf8(exported).unwrap(),
            &key,
            "binding-b",
        )
        .unwrap_err();
        assert!(error.starts_with("SPIKE-BE-SECURITY-S-0004"));
    }

    #[test]
    fn si_and_extension_worker_routes_are_not_pi_or_default_read_fallbacks() {
        assert_eq!(
            capability_for_worker(&json!({"method": "invoke_extension"})),
            "solver.extensions"
        );
        assert_eq!(
            capability_for_worker(&json!({"method": "run_analysis", "params": {"spec": {"analysis_type": "si"}}})),
            "si.solve"
        );
        assert_eq!(
            capability_for_worker(&json!({"method": "run_si_uniform_channel"})),
            "si.solve"
        );
        assert_eq!(
            capability_for_worker(&json!({"method": "run_owned_spice_workspace"})),
            "spice.execute"
        );
        assert_eq!(
            capability_for_worker(&json!({"method": "validate_si_protocol_suite"})),
            "project.read"
        );
    }
}
