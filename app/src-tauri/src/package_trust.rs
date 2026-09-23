use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use ed25519_dalek::{Signature, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const SIGNATURE_CONTRACT: &str = "spike/manifest-signature/v1";
const MAX_MANIFEST_BYTES: usize = 16 * 1024 * 1024;
const MAX_MANIFEST_BASE64URL_BYTES: usize = MAX_MANIFEST_BYTES.div_ceil(3) * 4;

fn manifest_size_error() -> String {
    "SPIKE-BE-PACKAGE-S-0002: canonical package manifest exceeds the 16 MiB limit".to_string()
}

fn ensure_manifest_size(payload: &[u8]) -> Result<(), String> {
    if payload.len() > MAX_MANIFEST_BYTES {
        return Err(manifest_size_error());
    }
    Ok(())
}

fn decode_canonical_manifest(signed_payload_base64url: &str) -> Result<Vec<u8>, String> {
    // Check the renderer-supplied text before the base64 decoder allocates its output buffer.
    if signed_payload_base64url.len() > MAX_MANIFEST_BASE64URL_BYTES {
        return Err(manifest_size_error());
    }
    let payload = URL_SAFE_NO_PAD
        .decode(signed_payload_base64url)
        .map_err(|_| {
            "SPIKE-BE-PACKAGE-S-0002: canonical package manifest is not valid base64url".to_string()
        })?;
    ensure_manifest_size(&payload)?;
    Ok(payload)
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PackageSignatureEnvelope {
    contract: String,
    algorithm: String,
    key_id: String,
    signed_payload_sha256: String,
    signature_base64url: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TrustedKeyRecord {
    key_id: String,
    public_key_base64url: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PackageTrustSummary {
    pub verified: bool,
    pub key_id: String,
    pub algorithm: &'static str,
    pub signed_payload_sha256: String,
}

#[derive(Debug)]
pub struct VerifiedProjectManifest {
    pub trust: PackageTrustSummary,
    pub manifest_payload_sha256: String,
}

fn configured_keys() -> Result<Vec<TrustedKeyRecord>, String> {
    if let Some(value) = option_env!("SPIKE_PACKAGE_TRUSTED_KEYS_JSON") {
        let records: Vec<TrustedKeyRecord> = serde_json::from_str(value).map_err(|error| {
            format!(
                "SPIKE-BE-PACKAGE-S-0004: the pinned package-key registry is malformed: {error}"
            )
        })?;
        if records.is_empty() {
            return Err(
                "SPIKE-BE-PACKAGE-S-0004: the pinned package-key registry is empty".to_string(),
            );
        }
        return Ok(records);
    }

    match (
        option_env!("SPIKE_PACKAGE_KEY_ID"),
        option_env!("SPIKE_PACKAGE_PUBLIC_KEY_B64URL"),
    ) {
        (Some(key_id), Some(public_key_base64url)) => Ok(vec![TrustedKeyRecord {
            key_id: key_id.to_string(),
            public_key_base64url: public_key_base64url.to_string(),
        }]),
        _ => {
            Err("SPIKE-BE-PACKAGE-S-0004: this build has no pinned package-signing key".to_string())
        }
    }
}

fn decode_verifying_key(record: &TrustedKeyRecord) -> Result<VerifyingKey, String> {
    let bytes = URL_SAFE_NO_PAD
        .decode(&record.public_key_base64url)
        .map_err(|_| {
            format!(
                "SPIKE-BE-PACKAGE-S-0004: pinned package key '{}' is not valid base64url",
                record.key_id
            )
        })?;
    let bytes: [u8; 32] = bytes.try_into().map_err(|_| {
        format!(
            "SPIKE-BE-PACKAGE-S-0004: pinned package key '{}' must be 32 bytes",
            record.key_id
        )
    })?;
    VerifyingKey::from_bytes(&bytes).map_err(|_| {
        format!(
            "SPIKE-BE-PACKAGE-S-0004: pinned package key '{}' is invalid",
            record.key_id
        )
    })
}

fn verify_with_records(
    signed_payload: &[u8],
    envelope: &PackageSignatureEnvelope,
    records: &[TrustedKeyRecord],
) -> Result<PackageTrustSummary, String> {
    if envelope.contract != SIGNATURE_CONTRACT || envelope.algorithm != "ed25519" {
        return Err(
            "SPIKE-BE-PACKAGE-S-0001: unsupported package signature contract or algorithm"
                .to_string(),
        );
    }

    let digest = hex::encode(Sha256::digest(signed_payload));
    if envelope.signed_payload_sha256 != digest {
        return Err(
            "SPIKE-BE-PACKAGE-S-0002: package signed-payload digest does not match".to_string(),
        );
    }

    let record = records
        .iter()
        .find(|record| record.key_id == envelope.key_id)
        .ok_or_else(|| {
            format!(
                "SPIKE-BE-PACKAGE-S-0004: package signing key '{}' is not trusted by this build",
                envelope.key_id
            )
        })?;
    let key = decode_verifying_key(record)?;
    let signature = URL_SAFE_NO_PAD
        .decode(&envelope.signature_base64url)
        .map_err(|_| {
            "SPIKE-BE-PACKAGE-S-0003: package signature is not valid base64url".to_string()
        })?;
    let signature = Signature::from_slice(&signature).map_err(|_| {
        "SPIKE-BE-PACKAGE-S-0003: package signature has the wrong length".to_string()
    })?;
    key.verify_strict(signed_payload, &signature).map_err(|_| {
        "SPIKE-BE-PACKAGE-S-0003: package signature verification failed".to_string()
    })?;

    Ok(PackageTrustSummary {
        verified: true,
        key_id: envelope.key_id.clone(),
        algorithm: "ed25519",
        signed_payload_sha256: digest,
    })
}

fn manifest_identity(signed_payload: &[u8]) -> Result<String, String> {
    let manifest: serde_json::Value = serde_json::from_slice(signed_payload).map_err(|error| {
        format!("SPIKE-BE-PACKAGE-S-0001: signed project manifest is invalid JSON: {error}")
    })?;
    let digest = manifest
        .get("manifest_payload_sha256")
        .and_then(serde_json::Value::as_str)
        .filter(|value| {
            value.len() == 64
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        })
        .ok_or_else(|| {
            "SPIKE-BE-PACKAGE-S-0001: signed project manifest identity is missing or malformed"
                .to_string()
        })?;
    Ok(digest.to_string())
}

fn verify_project_manifest_with_records(
    signed_payload: &[u8],
    envelope: &PackageSignatureEnvelope,
    records: &[TrustedKeyRecord],
) -> Result<VerifiedProjectManifest, String> {
    let trust = verify_with_records(signed_payload, envelope, records)?;
    Ok(VerifiedProjectManifest {
        trust,
        manifest_payload_sha256: manifest_identity(signed_payload)?,
    })
}

pub fn verify(
    signed_payload_base64url: &str,
    envelope: &PackageSignatureEnvelope,
) -> Result<PackageTrustSummary, String> {
    let payload = decode_canonical_manifest(signed_payload_base64url)?;
    verify_with_records(&payload, envelope, &configured_keys()?)
}

pub fn verify_project_manifest(
    signed_payload_base64url: &str,
    envelope: &PackageSignatureEnvelope,
) -> Result<VerifiedProjectManifest, String> {
    let payload = decode_canonical_manifest(signed_payload_base64url)?;
    verify_project_manifest_with_records(&payload, envelope, &configured_keys()?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    fn signed_fixture(payload: &[u8]) -> (PackageSignatureEnvelope, Vec<TrustedKeyRecord>) {
        let signing_key = SigningKey::from_bytes(&[17_u8; 32]);
        let signature = signing_key.sign(payload);
        (
            PackageSignatureEnvelope {
                contract: SIGNATURE_CONTRACT.to_string(),
                algorithm: "ed25519".to_string(),
                key_id: "test-package-root-v1".to_string(),
                signed_payload_sha256: hex::encode(Sha256::digest(payload)),
                signature_base64url: URL_SAFE_NO_PAD.encode(signature.to_bytes()),
            },
            vec![TrustedKeyRecord {
                key_id: "test-package-root-v1".to_string(),
                public_key_base64url: URL_SAFE_NO_PAD
                    .encode(signing_key.verifying_key().to_bytes()),
            }],
        )
    }

    #[test]
    fn verifies_a_manifest_with_a_pinned_key() {
        let payload = b"{\"format\":\"spike-project-package/v3\"}\n";
        let (envelope, records) = signed_fixture(payload);
        let summary = verify_with_records(payload, &envelope, &records).unwrap();
        assert!(summary.verified);
        assert_eq!(summary.key_id, "test-package-root-v1");
    }

    #[test]
    fn rejects_an_untrusted_key_identity() {
        let payload = b"{}\n";
        let (mut envelope, records) = signed_fixture(payload);
        envelope.key_id = "unknown-key".to_string();
        let error = verify_with_records(payload, &envelope, &records).unwrap_err();
        assert!(error.contains("SPIKE-BE-PACKAGE-S-0004"));
    }

    #[test]
    fn rejects_a_tampered_payload_digest() {
        let payload = b"{}\n";
        let (envelope, records) = signed_fixture(payload);
        let error = verify_with_records(b"{\"tampered\":true}\n", &envelope, &records).unwrap_err();
        assert!(error.contains("SPIKE-BE-PACKAGE-S-0002"));
    }

    #[test]
    fn rejects_a_tampered_signature() {
        let payload = b"{}\n";
        let (mut envelope, records) = signed_fixture(payload);
        envelope.signature_base64url = URL_SAFE_NO_PAD.encode([0_u8; 64]);
        let error = verify_with_records(payload, &envelope, &records).unwrap_err();
        assert!(error.contains("SPIKE-BE-PACKAGE-S-0003"));
    }

    #[test]
    fn rejects_an_oversized_encoded_manifest_before_decoding() {
        let encoded = "!".repeat(MAX_MANIFEST_BASE64URL_BYTES + 1);
        let error = decode_canonical_manifest(&encoded).unwrap_err();
        assert!(error.contains("exceeds the 16 MiB limit"));
    }

    #[test]
    fn rejects_an_oversized_decoded_manifest() {
        let payload = vec![0_u8; MAX_MANIFEST_BYTES + 1];
        let error = ensure_manifest_size(&payload).unwrap_err();
        assert!(error.contains("exceeds the 16 MiB limit"));
    }

    #[test]
    fn authenticated_project_identity_comes_from_the_signed_payload() {
        let identity = "a".repeat(64);
        let payload = format!(
            "{{\"format\":\"spike-project-package/v3\",\"manifest_payload_sha256\":\"{identity}\"}}\n"
        );
        let (envelope, records) = signed_fixture(payload.as_bytes());
        let verified = verify_project_manifest_with_records(
            payload.as_bytes(), &envelope, &records,
        )
        .unwrap();
        assert!(verified.trust.verified);
        assert_eq!(verified.manifest_payload_sha256, identity);
    }

    #[test]
    fn authenticated_project_identity_rejects_missing_manifest_identity() {
        let payload = b"{\"format\":\"spike-project-package/v3\"}\n";
        let (envelope, records) = signed_fixture(payload);
        let error = verify_project_manifest_with_records(payload, &envelope, &records).unwrap_err();
        assert!(error.contains("SPIKE-BE-PACKAGE-S-0001"));
    }
}
