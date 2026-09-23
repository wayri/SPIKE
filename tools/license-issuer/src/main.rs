use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use ed25519_dalek::{Signer, SigningKey};
use rand_core::OsRng;
use serde_json::{json, Value};
use std::{env, fs, path::Path};

fn required_string<'a>(claims: &'a Value, field: &str) -> Result<&'a str, String> {
    claims
        .get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("Claims field {field} must be a non-empty string"))
}

fn validate_claims(claims: &Value) -> Result<(), String> {
    if !claims.is_object() {
        return Err("Claims must be a JSON object".to_string());
    }
    let allowed_fields = [
        "schema",
        "license_id",
        "activation_id",
        "subject_id",
        "subject_name",
        "tier",
        "license_type",
        "capabilities",
        "product",
        "product_major",
        "issued_at",
        "not_before",
        "expires_at",
        "refresh_after",
        "device_public_key_sha256",
        "revocation_epoch",
        "organization_id",
        "offline",
    ];
    if let Some(field) = claims.as_object().and_then(|object| {
        object
            .keys()
            .find(|field| !allowed_fields.contains(&field.as_str()))
    }) {
        return Err(format!("Claims contain unsupported field {field}"));
    }
    if claims.get("schema").and_then(Value::as_str) != Some("spike/license-claims/v1") {
        return Err("Claims schema must be spike/license-claims/v1".to_string());
    }
    for field in [
        "license_id",
        "activation_id",
        "subject_id",
        "subject_name",
        "issued_at",
        "not_before",
    ] {
        required_string(claims, field)?;
    }
    if claims.get("product").and_then(Value::as_str) != Some("SPIKE")
        || claims.get("product_major").and_then(Value::as_u64) != Some(0)
    {
        return Err("Claims must target SPIKE product major 0".to_string());
    }
    let tier = required_string(claims, "tier")?;
    if !matches!(
        tier,
        "evaluation" | "professional" | "enterprise" | "developer"
    ) {
        return Err("Claims contain an unsupported license tier".to_string());
    }
    let license_type = required_string(claims, "license_type")?;
    if !matches!(
        license_type,
        "temporary" | "timed" | "perpetual" | "developer"
    ) {
        return Err("Claims contain an unsupported license type".to_string());
    }
    if license_type == "developer" && tier != "developer" {
        return Err("Developer licenses require the developer tier".to_string());
    }
    let expires_at = claims.get("expires_at").and_then(Value::as_str);
    if matches!(license_type, "temporary" | "timed" | "developer")
        && expires_at.is_none_or(|value| value.trim().is_empty())
    {
        return Err("Temporary, timed, and developer licenses require expires_at".to_string());
    }
    let capabilities = claims
        .get("capabilities")
        .and_then(Value::as_array)
        .filter(|values| {
            !values.is_empty()
                && values.iter().all(|value| {
                    value
                        .as_str()
                        .is_some_and(|capability| !capability.trim().is_empty())
                })
        })
        .ok_or_else(|| "Claims require at least one named capability".to_string())?;
    if capabilities.len() > 256 {
        return Err("Claims may contain at most 256 capabilities".to_string());
    }
    let binding = required_string(claims, "device_public_key_sha256")?;
    if binding.len() != 64
        || !binding
            .bytes()
            .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
    {
        return Err("device_public_key_sha256 must be a 64-character hex digest".to_string());
    }
    if claims
        .get("revocation_epoch")
        .and_then(Value::as_u64)
        .is_none()
    {
        return Err("revocation_epoch must be a non-negative integer".to_string());
    }
    if claims.get("offline").and_then(Value::as_bool).is_none() {
        return Err("offline must be a boolean".to_string());
    }
    Ok(())
}

fn usage() -> ! {
    eprintln!("Usage:\n  spike-license-issuer init <private-key-file>\n  spike-license-issuer issue <private-key-file> <claims-json> <entitlement-json> [key-id]");
    std::process::exit(2)
}

fn write_new_private_key(path: &Path) -> Result<(), String> {
    if path.exists() {
        return Err("Refusing to overwrite an issuer private key".to_string());
    }
    let signing = SigningKey::generate(&mut OsRng);
    fs::write(path, URL_SAFE_NO_PAD.encode(signing.to_bytes()))
        .map_err(|error| format!("Cannot write issuer private key: {error}"))?;
    println!(
        "SPIKE_LICENSE_PUBLIC_KEY_B64URL={}",
        URL_SAFE_NO_PAD.encode(signing.verifying_key().to_bytes())
    );
    println!("SPIKE_LICENSE_KEY_ID=spike-license-root-v1");
    Ok(())
}

fn load_signing_key(path: &Path) -> Result<SigningKey, String> {
    let encoded = fs::read_to_string(path)
        .map_err(|error| format!("Cannot read issuer private key: {error}"))?;
    let bytes = URL_SAFE_NO_PAD
        .decode(encoded.trim())
        .map_err(|_| "Issuer private key is not valid base64url".to_string())?;
    let bytes: [u8; 32] = bytes
        .try_into()
        .map_err(|_| "Issuer private key must contain 32 bytes".to_string())?;
    Ok(SigningKey::from_bytes(&bytes))
}

fn issue(
    private_key: &Path,
    claims_path: &Path,
    output_path: &Path,
    key_id: &str,
) -> Result<(), String> {
    if output_path.exists() {
        return Err("Refusing to overwrite an existing entitlement".to_string());
    }
    let signing = load_signing_key(private_key)?;
    let claims_bytes =
        fs::read(claims_path).map_err(|error| format!("Cannot read claims JSON: {error}"))?;
    let claims: Value = serde_json::from_slice(&claims_bytes)
        .map_err(|error| format!("Claims are not valid JSON: {error}"))?;
    validate_claims(&claims)?;
    let canonical = serde_json::to_vec(&claims).map_err(|error| error.to_string())?;
    let signature = signing.sign(&canonical);
    let envelope = json!({
        "schema": "spike/license-entitlement/v1",
        "key_id": key_id,
        "payload_base64url": URL_SAFE_NO_PAD.encode(&canonical),
        "signature_base64url": URL_SAFE_NO_PAD.encode(signature.to_bytes()),
    });
    fs::write(output_path, serde_json::to_vec_pretty(&envelope).unwrap())
        .map_err(|error| format!("Cannot write entitlement: {error}"))?;
    println!("Issued {}", output_path.display());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_claims() -> Value {
        json!({
            "schema": "spike/license-claims/v1",
            "license_id": "6ea91773-ab07-48d4-a9ee-9da24167589d",
            "activation_id": "7e039e70-2ab1-44a6-92e7-2a174578e2b8",
            "subject_id": "developer-1",
            "subject_name": "SPIKE Developer",
            "tier": "developer",
            "license_type": "developer",
            "capabilities": ["project.read", "solver.execute"],
            "product": "SPIKE",
            "product_major": 0,
            "issued_at": "2026-08-21T00:00:00Z",
            "not_before": "2026-08-21T00:00:00Z",
            "expires_at": "2026-09-21T00:00:00Z",
            "device_public_key_sha256": "a".repeat(64),
            "revocation_epoch": 0,
            "offline": true
        })
    }

    #[test]
    fn accepts_valid_developer_claims() {
        validate_claims(&valid_claims()).unwrap();
    }

    #[test]
    fn rejects_developer_claims_without_expiry() {
        let mut claims = valid_claims();
        claims["expires_at"] = Value::Null;
        assert!(validate_claims(&claims)
            .unwrap_err()
            .contains("require expires_at"));
    }

    #[test]
    fn rejects_malformed_device_binding() {
        let mut claims = valid_claims();
        claims["device_public_key_sha256"] = Value::String("not-a-binding".to_string());
        assert!(validate_claims(&claims)
            .unwrap_err()
            .contains("64-character hex digest"));
    }

    #[test]
    fn rejects_unknown_claim_fields() {
        let mut claims = valid_claims();
        claims["issuer_private_note"] = Value::String("must not be signed".to_string());
        assert!(validate_claims(&claims)
            .unwrap_err()
            .contains("unsupported field"));
    }
}

fn main() {
    let args = env::args().collect::<Vec<_>>();
    let result = match args.get(1).map(String::as_str) {
        Some("init") if args.len() == 3 => write_new_private_key(Path::new(&args[2])),
        Some("issue") if (5..=6).contains(&args.len()) => issue(
            Path::new(&args[2]),
            Path::new(&args[3]),
            Path::new(&args[4]),
            args.get(5)
                .map(String::as_str)
                .unwrap_or("spike-license-root-v1"),
        ),
        _ => usage(),
    };
    if let Err(error) = result {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
