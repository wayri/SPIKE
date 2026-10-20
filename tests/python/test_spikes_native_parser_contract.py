# SPDX-License-Identifier: Apache-2.0
"""Native CLI optimization retains the complete public option contract."""
import contextlib
import io
import os
from unittest.mock import patch
import unittest
from python.spikes.cli import _parser


class NativeParserContractTests(unittest.TestCase):
    def test_full_and_selected_command_accept_identical_options(self):
        cases = [
            ['native-run', 'deck.cir', '--library', 'engine.dll'],
            ['native-run', 'deck.cir', '--library', 'engine.dll', '--adaptive',
             '--method', 'bdf2', '--lte-absolute-tolerance', '2e-7',
             '--lte-relative-tolerance', '3e-4', '--minimum-time-step', '1e-12',
             '--max-rejected-steps', '27', '--probe', 'V(out)', '--probe', 'I(V1)', '-o', 'result.json'],
        ]
        for method in ('trap', 'hybrid_trapezoidal', 'be', 'bdf2', 'radau-iia3', 'radau_iia3'):
            cases.append(cases[0] + ['--method', method])
        for tokens in cases:
            with self.subTest(tokens=tokens):
                self.assertEqual(vars(_parser().parse_args(tokens)),
                                 vars(_parser(native_only=True).parse_args(tokens)))

    def test_rejections_and_native_help_are_identical(self):
        for tail in ([], ['deck.cir'], ['deck.cir', '--library', 'x', '--method', 'invalid'],
                     ['deck.cir', '--library', 'x', '--probe'],
                     ['deck.cir', '--library', 'x', '--unknown'], ['--help']):
            results=[]
            for selected in (False, True):
                text=io.StringIO()
                with contextlib.redirect_stdout(text), contextlib.redirect_stderr(text):
                    with self.assertRaises(SystemExit) as raised:
                        _parser(native_only=selected).parse_args(['native-run', *tail])
                results.append((raised.exception.code,text.getvalue()))
            self.assertEqual(*results)

    def test_global_help_retains_other_commands(self):
        help_text=_parser().format_help()
        for command in ('native-run','compile','check','run','ac','transfer','pdk','device-build'):
            self.assertIn(command,help_text)

    def test_help_preserves_actual_terminal_width(self):
        for width in ('42','140'):
            outputs=[]
            with patch.dict(os.environ,COLUMNS=width):
                for selected in (False,True):
                    text=io.StringIO()
                    with contextlib.redirect_stdout(text):
                        with self.assertRaises(SystemExit):
                            _parser(native_only=selected).parse_args(['native-run','--help'])
                    outputs.append(text.getvalue())
            self.assertEqual(*outputs)
