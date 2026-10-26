# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Reimport the pinned native WREN-Ie board and attempt bounded SI admission.

This fixture is the CERN native KiCad WREN-Ie design.  It is deliberately
distinct from the lossy legacy White Rabbit switch conversion evaluated by
``verify_si_real_boards.py``.  A completed run remains experimental evidence,
not a production, protocol, or compliance qualification.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_si_real_boards import evaluate


BOARD_PATH = "build/wren-si-fixture-20261023/EDA-04968-V2-0.kicad_pcb"
BOARD_SHA256 = "f98009ba98a0f7b302fe7c0f48fa64016a856af7d3989d3f6b7082435f9b2b9b"
HARDWARE_COMMIT = "816b7598a89151a8250fa5fa945d2a0154669325"
HARDWARE_PATH = "hw/EDA-04968-V2-0/EDA-04968-V2-0.kicad_pcb"
HARDWARE_URL = (
    "https://gitlab.cern.ch/be-cem-edl/chronos/wren/wren-hw/-/raw/"
    f"{HARDWARE_COMMIT}/{HARDWARE_PATH}"
)
LICENSE_COMMIT = "550e7d4f3e9f4288c7e04b05384c53e1fac44aa0"
LICENSE_ID = "CERN-OHL-W-2.0+"
LICENSE_URL = (
    "https://gitlab.com/ohwr/project/cernohl/-/raw/"
    f"{LICENSE_COMMIT}/licence_texts/cern_ohl_w_v2.txt"
)
REFERENCE_ZONE_ID = "ea044049-5fb5-596f-b5a6-61bcdbf83727"
DEFAULT_SIGNAL_NET = "/WR_CLK.ABSCAL"
SIGNAL_NET_CANDIDATES = (
    DEFAULT_SIGNAL_NET,
    "Net-(IC32-CLK)",
    "/WR_CLK.PPS",
    "/clocks/WR_CLKOUT_C_P",
    "/clocks/WR_CLKOUT_C_N",
    "/clocks/WR_CLKOUT_N",
    "/clocks/WR_CLKOUT_P",
    "Net-(IC1-RT{slash}CLK)",
)
COPPER_SCENARIO = {
    "conductivity_s_per_m": 58_000_000.0,
    "temperature_k": 293.15,
    "source": "https://www.npl.co.uk/products-services/magnetics/ac-and-dc-conductivity",
}
HASHED_OWNERS = (
    "scripts/verify_wren_si_scenario.py",
    "scripts/verify_si_real_boards.py",
    "python/spike_core/solvers/signal_integrity/channels/si_channel.py",
    "python/spike_core/solvers/signal_integrity/channels/si_material_scenario.py",
    "python/spike_core/service_project.py",
    "python/spike_core/kicad_importer.py",
    "python/spike_core/spider_v2.py",
)


def build_evidence(signal_net: str = DEFAULT_SIGNAL_NET) -> dict:
    """Evaluate one exact native net without simplifying its retained geometry."""
    if signal_net not in SIGNAL_NET_CANDIDATES:
        raise ValueError(f"Unsupported bounded WREN signal candidate: {signal_net}")
    spec = {
        "path": BOARD_PATH,
        "sha256": BOARD_SHA256,
        "signal_net": signal_net,
        "reference_net": "GND",
        "reference_layer": "In1.Cu",
        "conversion_losslessness_verified": None,
    }
    row = evaluate(
        "wren_ie_native",
        spec,
        copper_scenario=COPPER_SCENARIO,
        reference_zone_id=REFERENCE_ZONE_ID,
    )
    admitted = row["channel_admission"]["status"] == "admitted"
    return {
        "contract": "spike/si-native-wren-admission-evidence/v1",
        "board": row,
        "source_provenance": {
            "fixture_kind": "native_kicad_hardware",
            "hardware_project": "CERN WREN-Ie",
            "hardware_commit": HARDWARE_COMMIT,
            "hardware_repository_path": HARDWARE_PATH,
            "hardware_url": HARDWARE_URL,
            "source_sha256": BOARD_SHA256,
            "license_id": LICENSE_ID,
            "license_commit": LICENSE_COMMIT,
            "license_url": LICENSE_URL,
            "legacy_converted_white_rabbit_switch": False,
        },
        "selected_signal_candidate": signal_net,
        "channel_admission_passed": admitted,
        "production_qualified": False,
        "generation_specific_qualification": "not_evaluated",
        "assumptions": [
            "The copper conductivity is an explicit 58 MS/m nominal bulk-copper scenario at 293.15 K; it is not measured WREN PCB foil evidence.",
            "The selected clock path and 50 ohm reference are diagnostic inputs, not a WREN protocol or standard limit.",
            "No retained trace, via, arc, zone, stackup, or material geometry is simplified or invented to obtain admission.",
            "A passing bounded model is experimental and is not production, protocol, or compliance qualification.",
        ],
        "source_sha256": {
            name: sha256((ROOT / name).read_bytes()).hexdigest()
            for name in HASHED_OWNERS
        },
    }


def write_evidence(output: Path, evidence: dict) -> None:
    with output.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--signal-net", choices=SIGNAL_NET_CANDIDATES, default=DEFAULT_SIGNAL_NET)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("A fresh output file is required")
    evidence = build_evidence(args.signal_net)
    write_evidence(args.output, evidence)
    row = evidence["board"]
    print(json.dumps({
        "signal_net": args.signal_net,
        "strict_uniform": row["path_modes"]["strict_uniform"]["status"],
        "piecewise_planar": row["path_modes"]["piecewise_planar"]["status"],
        "channel_admission_passed": evidence["channel_admission_passed"],
        "production_qualified": False,
    }))
    return 0 if evidence["channel_admission_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
