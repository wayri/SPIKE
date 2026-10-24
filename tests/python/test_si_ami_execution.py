# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original native synthetic ABI tests; build fixtures to enable executable cases."""
from hashlib import sha256
import math
import os
from pathlib import Path
import struct
import time
import unittest
from unittest.mock import patch

from python.spike_core import si_ami_execution as ami

ROOT = Path(__file__).resolve().parents[2]
BIN = Path(os.environ.get("SPIKE_AMI_TEST_BIN", str(ROOT / "build-ami-host" / "Release")))
DOCUMENT = '''(CopperFox (Reserved_Parameters
 (AMI_Version (Usage Info) (Type String) (Value "8.0"))
 (Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True))
 (GetWave_Exists (Usage Info) (Type Boolean) (Value True))))'''


def member(path):
    return {"path": str(path.resolve()), "sha256": sha256(path.read_bytes()).hexdigest()}


def request(mode=0):
    return {"contract": ami.REQUEST_CONTRACT, "platform": "windows-x86_64", "direction": "rx",
            "model_file": member(BIN / f"ami_fixture_{mode}.dll"), "dependencies": [],
            "trust": {"acknowledgement": ami.TRUST_ACKNOWLEDGEMENT, "license_reviewed": True, "dependency_reviewed": True},
            "parameter_text": DOCUMENT, "sample_interval_s": 1e-12, "symbol_time_s": 4e-12,
            "impulse_response": [1., 0., 0., 0.], "wave_blocks": [[-1., 0., 1.], [0., -1., 1., 0.]],
            "timeout_s": 3., "memory_limit_mib": 128}


class AdmissionTests(unittest.TestCase):
    def test_parameter_defaults_and_unknown_semantics(self):
        source = DOCUMENT[:-1] + '(Model_Specific (Gain (Usage In) (Type Float) (Value 2))))'
        _, selected = ami._parameter_input(source)
        self.assertEqual(selected, '(CopperFox (Gain 2.0))')
        source = DOCUMENT.replace('(GetWave_Exists', '(Rx_Use_Clock_Input (Usage Info) (Type String) (Value "Times")) (GetWave_Exists')
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'reserved'):
            ami._parameter_input(source)

    def test_pe_malformed_never_loads(self):
        for value in (b'', b'MZ', b'MZ' + b'\0' * 500):
            with self.subTest(length=len(value)), self.assertRaises(ami.SiAmiExecutionError):
                ami._pe_system_imports(value, dll=True)

    def test_output_bounds_and_root_mismatch(self):
        def text(value): return struct.pack('<I', len(value)) + value
        malformed = b'SPKAMO1\0' + struct.pack('<I', 0) + text(b'') + text(b'(Different)')
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'root'):
            ami._decode(malformed, {}, 'CopperFox')
        for payload in (b'', b'SPKAMO1\0', b'SPKAMO1\0' + struct.pack('<II', 0, 20000)):
            with self.assertRaises(ami.SiAmiExecutionError):
                ami._decode(payload, {}, 'CopperFox')

    def test_complete_output_parameter_tree_syntax(self):
        for value in ('(CopperFox)', '(CopperFox (Gain 1.25) (Group (Enabled True) (Text "x | y")))',
                      '(CopperFox (Taps 1 .5 -2e-3))'):
            self.assertEqual(ami._output_parameters(value, 'CopperFox'), value)
        for value in ('(CopperFox malformed', '(CopperFox (Gain 1)', '(CopperFox) trailing',
                      '(CopperFox) (Other)', '(CopperFox bare)', '(CopperFox (Mixed 1 (Nested 2)))',
                      '(CopperFox (Gain nonnumeric))', '(CopperFox ())', '(CopperFox)|comment',
                      '(CopperFox (Gain 1e999))', '(CopperFox (Empty))'):
            with self.subTest(value=value), self.assertRaises(ami.SiAmiExecutionError):
                ami._output_parameters(value, 'CopperFox')


@unittest.skipUnless(os.name == 'nt' and (BIN / 'spike-ami-host.exe').is_file(),
                     'build native AMI fixtures; set SPIKE_AMI_TEST_BIN if needed')
class NativeExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = member(BIN / 'spike-ami-host.exe')

    def run_model(self, value, **kwargs):
        return ami.execute_ami_native(value, host_path=self.host['path'], host_sha256=self.host['sha256'],
                                      job_parent=str(BIN.parent), **kwargs)

    def test_identity_init_wave_close_and_pam3_levels(self):
        value = request()
        result = self.run_model(value)
        self.assertEqual(result['impulse_response'], value['impulse_response'])
        self.assertEqual([b['wave'] for b in result['blocks']], value['wave_blocks'])
        self.assertEqual(result['blocks'][0]['clock_times_s'], [0.])
        self.assertAlmostEqual(result['blocks'][1]['clock_times_s'][0], 3e-12, delta=1e-26)
        self.assertFalse(result['sandboxed'])
        self.assertEqual(result['model_status'], 'experimental')
        self.assertEqual(result['provenance']['os_enforcement'], 'windows_job_object')

    def test_fir_and_stateful_partition_equivalence(self):
        for mode in (1, 2):
            value = request(mode)
            source = sum(value['wave_blocks'], [])
            expected, previous = [], 0.
            for sample in source:
                output = .75 * sample + .25 * previous if mode == 1 else .5 * sample + .5 * previous
                expected.append(output)
                previous = sample if mode == 1 else output
            result = self.run_model(value)
            self.assertEqual(sum((b['wave'] for b in result['blocks']), []), expected)
            value['wave_blocks'] = [source]
            self.assertEqual(self.run_model(value)['blocks'][0]['wave'], expected)
            self.assertEqual(result['impulse_response'], [0.75, .25, 0., 0.] if mode == 1 else [.5, .25, .125, .0625])

    def test_continuous_impulse_area_and_constant_gain(self):
        # An AMI unit-area continuous-time impulse sample is 1/dt, not 1.
        # Exercise three sample intervals without using dimensionless FIR
        # metadata as the continuous-time Init impulse oracle.
        for interval in (1e-12, 2e-12, 5e-12):
            for mode, gain in ((0, 1.), (1, 1.), (15, 2.)):
                value = request(mode)
                value['sample_interval_s'] = interval
                value['symbol_time_s'] = 4 * interval
                value['impulse_response'] = [1. / interval, 0., 0., 0.]
                result = self.run_model(value)
                area = math.fsum(result['impulse_response']) * interval
                self.assertAlmostEqual(area, gain, delta=5e-15)
                if mode == 15:
                    self.assertEqual(result['impulse_response'][0], 2. / interval)
                    self.assertEqual(result['blocks'][0]['wave'], [-2., 0., 2.])

    def test_init_only_and_tx(self):
        value = request()
        value['wave_blocks'] = []
        value['parameter_text'] = DOCUMENT.replace('(GetWave_Exists (Usage Info) (Type Boolean) (Value True))',
                                                 '(GetWave_Exists (Usage Info) (Type Boolean) (Value False))')
        self.assertEqual(self.run_model(value)['blocks'], [])
        value = request()
        value['direction'] = 'tx'
        self.assertEqual(self.run_model(value)['blocks'][0]['clock_times_s'], [])
        value = request()
        value['parameter_text'] = DOCUMENT.replace('(Init_Returns_Impulse (Usage Info) (Type Boolean) (Value True))',
                                                 '(Init_Returns_Impulse (Usage Info) (Type Boolean) (Value False))')
        result = self.run_model(value)
        self.assertIsNone(result['impulse_response'])
        self.assertFalse(result['init_returns_impulse'])

    def test_job_disallows_descendant_process(self):
        result = self.run_model(request(13))
        self.assertEqual(result['init_parameters_out'], '(CopperFox (ChildDenied True))')

    def test_lifecycle_failures_and_invalid_outputs(self):
        for mode, message in ((3, 'AMI_Init'), (4, 'AMI_GetWave'), (5, 'AMI_Close'), (6, 'result'),
                              (8, 'non-finite'), (9, 'clock'), (10, 'clock'), (11, 'root'), (12, 'export'),
                              (14, 'parameter tree'), (16, 'parameter tree')):
            with self.subTest(mode=mode), self.assertRaisesRegex(ami.SiAmiExecutionError, message):
                self.run_model(request(mode))
        self.assertEqual(self.run_model(request())['model_status'], 'experimental')

    def test_timeout_and_cancellation(self):
        value = request(7)
        value['timeout_s'] = .15
        started = time.monotonic()
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'timeout'):
            self.run_model(value)
        self.assertLess(time.monotonic() - started, 5)
        value['timeout_s'] = 3
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'cancelled'):
            self.run_model(value, cancelled=lambda: True)

    def test_rejections_precede_spawn(self):
        changes = [({'dependencies': ['unreviewed.dll']}, 'dependencies'),
                   ({'platform': 'linux-x86_64'}, 'Windows'), ({'timeout_s': math.nan}, 'finite'),
                   ({'wave_blocks': [[1.] * (ami.MAX_SAMPLES + 1)]}, 'samples'),
                   ({'memory_limit_mib': True}, 'memory'), ({'direction': 'other'}, 'direction')]
        for change, error in changes:
            value = request(); value.update(change)
            with self.subTest(change=list(change)), patch.object(ami, 'supervise_process') as runner:
                with self.assertRaisesRegex(ami.SiAmiExecutionError, error):
                    self.run_model(value)
                runner.assert_not_called()
        value = request(); value['model_file']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'SHA-256'):
            self.run_model(value)
        value = request(); value['trust']['license_reviewed'] = False
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'trust'):
            self.run_model(value)
        value = request(); value['trust']['license_reviewed'] = 1
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'trust'):
            self.run_model(value)

    def test_pe_dependency_and_platform_rejection(self):
        original = bytearray((BIN / 'ami_fixture_0.dll').read_bytes())
        pe = struct.unpack_from('<I', original, 0x3c)[0]
        wrong_arch = bytearray(original)
        struct.pack_into('<H', wrong_arch, pe + 4, 0x14c)
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'AMD64'):
            ami._pe_system_imports(bytes(wrong_arch), dll=True)
        self.assertIn('kernel32.dll', ami._pe_system_imports(bytes(original), dll=True))
        name_start = bytes(original).lower().find(b'kernel32.dll\0')
        self.assertGreater(name_start, 0)
        original[name_start:name_start + 12] = b'unreview.dll'
        with self.assertRaisesRegex(ami.SiAmiExecutionError, 'dependency'):
            ami._pe_system_imports(bytes(original), dll=True)

    def test_maximum_sample_budget(self):
        value = request()
        value['wave_blocks'] = [[0.] * ami.MAX_SAMPLES]
        result = self.run_model(value)
        self.assertEqual(len(result['blocks'][0]['wave']), ami.MAX_SAMPLES)


if __name__ == '__main__':
    unittest.main()
