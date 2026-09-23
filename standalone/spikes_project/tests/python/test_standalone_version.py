from __future__ import annotations

import unittest

import python.spikes as spikes
from python.spikes.cli import CLI_VERSION
from python.spikes.library import LIBRARY_VERSION
from python.spikes.version import ENGINE_VERSION


class StandaloneVersionTests(unittest.TestCase):
    def test_all_runtime_surfaces_share_the_canonical_version(self) -> None:
        self.assertEqual(spikes.__version__, ENGINE_VERSION)
        self.assertEqual(CLI_VERSION, ENGINE_VERSION)
        self.assertEqual(LIBRARY_VERSION, ENGINE_VERSION)


if __name__ == "__main__":
    unittest.main()
