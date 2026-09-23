"""Shared manifest-signature policy for targeted package readers."""

from __future__ import annotations

from typing import Mapping

from .project_package import (
    ManifestVerifier,
    ProjectPackageError,
    _validate_signature_envelope,
    manifest_signature_payload,
)


def validate_targeted_manifest_signature(
    manifest: Mapping[str, object],
    *,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> None:
    """Apply full-package signature semantics after a targeted manifest read."""

    if "signature" not in manifest:
        if require_signature:
            raise ProjectPackageError("A signed package manifest is required.")
        return
    raw_signature = manifest.get("signature")
    if not isinstance(raw_signature, Mapping):
        raise ProjectPackageError("Package manifest signature must be an object.")

    signed_payload = manifest_signature_payload(manifest)
    signature = _validate_signature_envelope(raw_signature, signed_payload)
    if signature_verifier is None:
        if require_signature:
            raise ProjectPackageError("A trusted manifest verifier is required for this package.")
        return
    try:
        verified = bool(signature_verifier(signed_payload, signature))
    except Exception as exc:
        raise ProjectPackageError("Package manifest signature verification failed.") from exc
    if not verified:
        raise ProjectPackageError("Package manifest signature verification failed.")
