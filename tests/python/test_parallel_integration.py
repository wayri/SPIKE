# SPDX-License-Identifier: Apache-2.0
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
from python.spike_core.parallel_pool import validate_batch


class ParallelIntegrationTests(unittest.TestCase):
    def test_example_schema_and_dedicated_cli_run(self):
        path = Path('examples/parallel/harness-batch.json')
        request = json.loads(path.read_text(encoding='utf-8'))
        schema = json.loads(Path('schemas/parallel-batch-v1.schema.json').read_text())
        Draft202012Validator(schema).validate(request)
        self.assertEqual(validate_batch(request), request)
        result = subprocess.run([sys.executable, '-m', 'python.spike_core.cluster_cli',
                                 'parallel-run', str(path)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['status'], 'completed', payload)
        self.assertEqual([item['id'] for item in payload['outcomes']], ['load-2A', 'load-3A'])

    def test_source_packaged_child_entry_and_frozen_command_prefix(self):
        from unittest.mock import patch
        from python.spike_core.parallel_pool import _command
        with patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(_command(), [sys.executable, '--parallel-child'])
        request = json.loads(Path('examples/parallel/harness-batch.json').read_text())['jobs'][0]
        response = subprocess.run([sys.executable, 'scripts/spike_worker_entry.py', '--parallel-child'],
                                  input=json.dumps(request).encode(), capture_output=True, timeout=30)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertTrue(json.loads(response.stdout)['ok'])

    def test_service_and_mcp_catalogs_reject_extra_configuration(self):
        from python.spike_core.service import handle
        from python.spike_core.mcp_server import TOOLS
        response = handle({'method': 'parallel_pool_catalog', 'params': {}})
        self.assertTrue(response['ok'])
        self.assertIn('spike_parallel_run', TOOLS)
        response = handle({'method': 'run_parallel_batch', 'params': {'request': {}, 'executable': 'anything'}})
        self.assertFalse(response['ok'])

    def test_dedicated_node_entry_does_not_import_extension_service(self):
        program = ('import sys; from python.spike_core.cluster_cli import main; '
                   'main(["parallel-pool"]); '
                   'assert "python.spike_core.service" not in sys.modules; '
                   'assert "python.spike_core.extensions" not in sys.modules')
        result = subprocess.run([sys.executable, '-c', program], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
