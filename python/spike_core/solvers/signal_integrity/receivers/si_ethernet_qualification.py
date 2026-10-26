# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Fail-closed scope assessment for the bounded 10 GbE SI evidence.

This module classifies evidence; it does not implement an IEEE 802.3 test
procedure or turn generic SI results into protocol-compliance evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


CONTRACT = "spike/si-10gbe-evidence-assessment/v1"
SUPPORTED_MODES = ("10GBASE-KR", "10GBASE-T", "10GBASE-SR", "10GBASE-LR")

_MODE_GATES = {
    "10GBASE-KR": {
        "medium": "electrical_backplane",
        "required": {
            "differential_channel_fixture", "specified_transmitter",
            "specified_receiver_equalization", "dynamic_cdr", "jitter_noise",
            "link_training", "normative_test_vectors", "independent_correlation",
        },
    },
    "10GBASE-T": {
        "medium": "four_pair_balanced_copper",
        "required": {
            "four_pair_bidirectional_fixture", "pam16_dsq_phy", "echo_cancellation",
            "next_fext_cancellation", "timing_recovery", "ldpc_coding_training",
            "normative_test_vectors", "independent_correlation",
        },
    },
    "10GBASE-SR": {
        "medium": "850_nm_multimode_optical",
        "required": {
            "optical_transmitter_fixture", "multimode_fiber_fixture",
            "optical_receiver_fixture", "optical_power_penalty_tests",
            "normative_test_vectors", "independent_correlation",
        },
    },
    "10GBASE-LR": {
        "medium": "1310_nm_single_mode_optical",
        "required": {
            "optical_transmitter_fixture", "single_mode_fiber_fixture",
            "optical_receiver_fixture", "optical_power_penalty_tests",
            "normative_test_vectors", "independent_correlation",
        },
    },
}


def assess_10gbe_evidence(
    mode: str,
    evidence: Iterable[str],
    *,
    reference_rate_hz: float | None = None,
) -> dict[str, Any]:
    """Return a deterministic qualification boundary for one explicit PHY mode."""
    if mode not in _MODE_GATES:
        raise ValueError(f"mode must be one of {', '.join(SUPPORTED_MODES)}")
    supplied = {str(item) for item in evidence}
    gate = _MODE_GATES[mode]
    missing = sorted(gate["required"] - supplied)
    numerical_core = "linear_nrz_10_3125_gbd_reference" in supplied
    rate_matches = reference_rate_hz == 10_312_500_000.0
    exploratory_scope = (
        "kr_linear_nrz_numerical_foundation" if mode == "10GBASE-KR" and
        numerical_core and rate_matches else "none"
    )
    # Even a complete list is only an inventory assertion. Protocol compliance
    # needs an approved standards-specific procedure and reviewed result bundle.
    return {
        "contract": CONTRACT,
        "mode": mode,
        "medium": gate["medium"],
        "reference_rate_hz": reference_rate_hz,
        "exploratory_scope": exploratory_scope,
        "missing_evidence": missing,
        "evidence_inventory_complete": not missing,
        "pcb_channel_extraction_qualified": False,
        "production_qualified": False,
        "compliance_status": "not_evaluated",
        "can_claim_protocol_compliance": False,
    }
