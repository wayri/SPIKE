# SPDX-License-Identifier: Apache-2.0
#!/usr/bin/env python3
"""Bundle the pinned ESP32 request and solved board grid for SPIKE viewport review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "esp32"
SOURCE = EXAMPLE / "source" / "iot-esp-eth-ind.kicad_pcb"
REQUEST = EXAMPLE / "layered_thermal_run.json"
RESULT = EXAMPLE / "evidence" / "layered_thermal_result.json"
OUTPUT = EXAMPLE / "evidence" / "thermal_view_bundle.json"
PINNED_SHA256 = "3199ce0a25f8987020e716d82a4a35d9b6b04541d33b2f2e46406376713eab33"


def main() -> None:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != PINNED_SHA256:
        raise ValueError("ESP32 board source changed; regenerate and review the thermal result first.")
    request_source = json.loads(REQUEST.read_text(encoding="utf-8"))
    request = request_source["request"]
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    if result.get("contract") != "spike/board-thermal-result/v1" or result.get("status") != "completed":
        raise ValueError("Saved layered board thermal result is not completed.")
    bundle = {
        "contract": "spike/board-thermal-view-bundle/v1",
        "source_board_sha256": digest,
        "source_board": "examples/esp32/source/iot-esp-eth-ind.kicad_pcb",
        "request": request,
        "result": result,
    }
    OUTPUT.write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
