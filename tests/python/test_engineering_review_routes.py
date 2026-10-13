# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import tempfile
import unittest
from python.spike_core.service import handle, validate_design
from python.spike_core.cli import build_parser, dispatch
from python.spike_core.contracts import SpiDeR
from tests.python.test_engineering_review import request


class EngineeringReviewRouteTests(unittest.TestCase):
    def test_worker_and_cli_use_the_same_review(self):
        value=request()
        response=handle({'method':'review_engineering','params':{'request':value}})
        self.assertTrue(response['ok'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'review.json'
            path.write_text(json.dumps(value),encoding='utf-8')
            result,code=dispatch(build_parser().parse_args(['engineering-review','--request',str(path)]))
        self.assertEqual(code,0)
        self.assertEqual(result,response['result'])
        self.assertFalse(handle({'method':'review_engineering','params':{}})['ok'])

    def test_calculator_route_and_design_validation_reexport(self):
        value={'contract':'spike/quick-engineering-tool-request/v1','tool':'resistor_divider',
               'vin':'5','r_top_ohm':'10000','r_bottom_ohm':'10000'}
        response=handle({'method':'quick_engineering_tool','params':{'request':value}})
        self.assertEqual(response['result']['result']['vout_v'],'2.5')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'calculator.json'
            path.write_text(json.dumps(value),encoding='utf-8')
            result,code=dispatch(build_parser().parse_args(['quick-tool','--request',str(path)]))
        self.assertEqual(code,0)
        self.assertEqual(result,response['result'])
        # Existing callers keep the central module's exported design checker.
        validation=validate_design(SpiDeR())
        self.assertFalse(validation['valid'])
        self.assertTrue(any(issue['code']=='NO_CONDUCTIVE_GEOMETRY' for issue in validation['issues']))
