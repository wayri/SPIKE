from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class StudioContractTests(unittest.TestCase):
    def test_ai_draft_contract_fails_closed(self) -> None:
        schema = json.loads((ROOT / "studio/schemas/studio-ai-model-draft-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["execution"]["properties"]["allowed"]["const"], False)
        self.assertEqual(schema["properties"]["qualification"]["properties"]["state"]["const"], "unreviewed")

    def test_deployment_contract_has_sil_pil_hil_and_provenance(self) -> None:
        schema = json.loads((ROOT / "studio/schemas/studio-deployment-model-v1.schema.json").read_text(encoding="utf-8"))
        targets = schema["properties"]["target"]["enum"]
        self.assertTrue({"sil", "pil", "hil", "observer", "control_plant"}.issubset(targets))
        self.assertIn("provenance", schema["required"])


if __name__ == "__main__":
    unittest.main()
