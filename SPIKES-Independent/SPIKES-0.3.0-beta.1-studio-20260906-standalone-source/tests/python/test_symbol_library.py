from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SymbolLibraryTests(unittest.TestCase):
    def test_core_symbols_have_unique_ids_and_grid_aligned_terminals(self) -> None:
        library = json.loads(
            (ROOT / "studio/library/core-symbols-v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(library["contract"], "spikes/studio-symbol-library/v1")
        identifiers = [symbol["id"] for symbol in library["symbols"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertGreaterEqual(len(identifiers), 6)
        for symbol in library["symbols"]:
            with self.subTest(symbol=symbol["id"]):
                grid = symbol["grid"]
                terminal_ids = [terminal["id"] for terminal in symbol["terminals"]]
                self.assertEqual(len(terminal_ids), len(set(terminal_ids)))
                for terminal in symbol["terminals"]:
                    self.assertTrue(terminal["connection_indicator"])
                    for coordinate in terminal["at"]:
                        self.assertAlmostEqual(coordinate / grid, round(coordinate / grid))
                    self.assertNotEqual(terminal["at"], terminal["leg_endpoint"])
                self.assertIn("body_keepout", symbol)
                self.assertIn("label_keepouts", symbol)


if __name__ == "__main__":
    unittest.main()
