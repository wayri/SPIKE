"""Security and licensing error specifications for the canonical catalog.

The tuples are data-only so :mod:`spike_core.errors` remains the single owner
of parsing, metadata construction, redaction, and envelope behavior.
"""

from __future__ import annotations


SECURITY_ERROR_SPECS = (
    (
        "SPIKE-FE-SECURITY-E-0001",
        "Desktop license service unavailable",
        "The licensing operation requires the native SPIKE desktop host.",
        True,
        True,
        "Open the installed SPIKE desktop application and retry the licensing operation.",
    ),
    (
        "SPIKE-BE-SECURITY-S-0001",
        "License issuer trust unavailable",
        "The desktop build has no usable pinned license issuer key.",
        False,
        False,
        "Install an official SPIKE build containing the expected issuer public key.",
    ),
    (
        "SPIKE-BE-SECURITY-S-0002",
        "License envelope invalid",
        "The entitlement envelope is malformed, unsupported, or exceeds its safety limit.",
        True,
        False,
        "Obtain a fresh entitlement from an authorized SPIKE issuer.",
    ),
    (
        "SPIKE-BE-SECURITY-S-0003",
        "License signature invalid",
        "The entitlement signature does not verify against the pinned issuer key.",
        True,
        False,
        "Do not use the entitlement; obtain a fresh signed entitlement from an authorized issuer.",
    ),
    (
        "SPIKE-BE-SECURITY-S-0004",
        "License device binding mismatch",
        "The entitlement is bound to a different machine or operating-system user.",
        True,
        False,
        "Deactivate the previous seat or issue a new entitlement for this device-user binding.",
    ),
    (
        "SPIKE-BE-SECURITY-E-0001",
        "License claims invalid",
        "Required entitlement claims are missing, inconsistent, or unsupported.",
        True,
        False,
        "Correct the issuer claims and issue a new signed entitlement.",
    ),
    (
        "SPIKE-BE-SECURITY-E-0002",
        "License product mismatch",
        "The entitlement targets a different product or incompatible major version.",
        True,
        False,
        "Use an entitlement issued for this SPIKE product major version.",
    ),
    (
        "SPIKE-BE-SECURITY-E-0003",
        "License validity period rejected",
        "The entitlement is not yet valid or has expired.",
        True,
        False,
        "Renew the entitlement or correct the trusted system clock before activating again.",
    ),
    (
        "SPIKE-BE-SECURITY-E-0004",
        "License storage failed",
        "The desktop host could not read, stage, replace, or remove the local entitlement.",
        True,
        True,
        "Check per-user application-data permissions and available disk space, then retry.",
    ),
    (
        "SPIKE-BE-SECURITY-E-0005",
        "License not installed",
        "No signed entitlement is installed for the current machine and user.",
        True,
        False,
        "Activate a signed temporary, timed, perpetual, or developer entitlement.",
    ),
    (
        "SPIKE-BE-SECURITY-E-0006",
        "Licensed capability required",
        "The installed entitlement does not grant the requested protected operation.",
        True,
        False,
        "Install an entitlement containing the required capability or continue in viewer mode.",
    ),
)


__all__ = ["SECURITY_ERROR_SPECS"]
