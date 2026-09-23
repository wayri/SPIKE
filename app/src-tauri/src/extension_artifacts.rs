//! Bounded, digest-checked extension artifact decoding before the save dialog.
use base64::Engine;
use sha2::{Digest, Sha256};

pub fn file_name(name: &str) -> Result<String, String> {
    if name.is_empty() || name.len() > 240 || name.chars().any(|c| c.is_control() || "/\\:".contains(c)) {
        return Err("Artifact must have a plain filename without a path".into());
    }
    let suffix = name.rsplit('.').next().unwrap_or("").to_ascii_lowercase();
    if !["step", "stp", "zip", "json", "fcstd", "brep"].contains(&suffix.as_str()) {
        return Err("Unsupported extension export file type".into());
    }
    Ok(name.to_owned())
}

pub fn decode(data: &str, encoding: &str, sha256: &str) -> Result<Vec<u8>, String> {
    const MAX: usize = 64 * 1024 * 1024;
    if data.len() > (MAX / 3 + 1) * 4 {
        return Err("Extension artifact exceeds 64 MiB".into());
    }
    let payload = match encoding {
        "base64" => base64::engine::general_purpose::STANDARD.decode(data)
            .map_err(|_| "Invalid extension artifact base64".to_string())?,
        "utf-8" => data.as_bytes().to_vec(),
        _ => return Err("Unsupported extension artifact encoding".into()),
    };
    if payload.is_empty() || payload.len() > MAX {
        return Err("Extension artifact is empty or exceeds 64 MiB".into());
    }
    if hex::encode(Sha256::digest(&payload)) != sha256 {
        return Err("Extension artifact digest mismatch".into());
    }
    Ok(payload)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn checks_bytes_and_digest_before_saving() {
        let digest = hex::encode(Sha256::digest(b"STEP"));
        assert_eq!(decode("U1RFUA==", "base64", &digest).unwrap(), b"STEP");
        assert_eq!(decode("STEP", "utf-8", &digest).unwrap(), b"STEP");
        assert!(decode("U1RFUA==", "base64", "bad").is_err());
        assert!(decode("bad%", "base64", &digest).is_err());
        assert!(decode("STEP", "binary", &digest).is_err());
        assert!(decode("", "utf-8", &hex::encode(Sha256::digest(b""))).is_err());
    }
    #[test]
    fn rejects_paths_and_executable_suggestions() {
        assert_eq!(file_name("assembly.FCStd").unwrap(), "assembly.FCStd");
        for name in ["../assembly.zip", "..\\assembly.zip", "C:\\assembly.step", "assembly.exe", "bad\n.zip", ""] {
            assert!(file_name(name).is_err());
        }
    }
}
