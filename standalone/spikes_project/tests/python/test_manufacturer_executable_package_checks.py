# SPDX-License-Identifier: Apache-2.0
"""Source-check the bounded frozen manufacturer-model acceptance helper."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))
sys.path.insert(0, str(ROOT))

DEFAULT_LIBRARY = ROOT / "build-spikes-native-analysis-20261013/Release/spikes_c_api.dll"
LIBRARY = Path(os.environ.get("SPIKES_TEST_LIBRARY", DEFAULT_LIBRARY))


class ManufacturerExecutablePackageChecksTests(unittest.TestCase):
    def test_helper_has_no_firmware_or_gui_runtime_dependency(self):
        from spikes_studio import manufacturer_executable_package_checks as checks
        source = Path(checks.__file__).read_text(encoding="utf-8")
        self.assertNotIn("firmware", source.casefold())
        self.assertNotIn("import wx", source.casefold())

    @unittest.skipUnless(LIBRARY.is_file(), "Set SPIKES_TEST_LIBRARY to a current native library")
    def test_bundled_catalog_and_all_five_native_recipes_execute(self):
        from spikes_studio.manufacturer_executable_package_checks import verify

        passed = []
        def check(value, label):
            self.assertTrue(value, label)
            passed.append(label)

        verify(LIBRARY, check)
        self.assertEqual(sum(label.endswith("packaged native recipe executes") for label in passed), 5)
        self.assertEqual(sum(label.endswith("packaged native result matches bounded oracle") for label in passed), 5)
        self.assertIn("manufacturer executable catalog JSON bundled", passed)


if __name__ == "__main__":
    unittest.main()
