# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio import toolchains

class ToolchainTests(unittest.TestCase):
    def test_config_is_inert_roundtrip_and_invalid_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'new-profile/settings.json';exe=Path(directory)/'compiler.exe';exe.write_text('not executed')
            with patch.object(toolchains,'settings_path',return_value=target):
                toolchains.save({'iverilog':str(exe)})
                self.assertEqual(toolchains.configured('iverilog'),str(exe))
                target.write_text('{bad');self.assertIsNone(toolchains.configured('iverilog'))
                with self.assertRaises(ValueError):toolchains.load()
                with self.assertRaises(ValueError):toolchains.save({'iverilog':'relative.exe'})
                with self.assertRaises(ValueError):toolchains.save({'unknown':str(exe)})
                toolchains.save({});self.assertEqual(toolchains.load(),{})
