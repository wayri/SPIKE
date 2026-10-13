# SPDX-License-Identifier: Apache-2.0
"""Actual TLS/child-process tests using disposable independently generated keys."""
import copy
import json
from pathlib import Path
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from python.spike_core.cluster_protocol import (CONTRACT, ClusterError, MAX_FRAME,
                                                digest, fingerprint, receive, strict_json)
from python.spike_core.cluster_transport import NodeServer, node_request, tls_context
from python.spike_core.cluster_manager import load_pool, probe_pool, run_cluster_batch
from python.spike_core.parallel_pool import pool_catalog, run_parallel_batch
from tests.python.test_harness_pi import fixture


class ProtocolTests(unittest.TestCase):
    def test_strict_values_shapes_and_budgets(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'[]', b'{',
                    b'{"x":' + b'[' * 35 + b'0' + b']' * 35 + b'}']:
            with self.assertRaises(ClusterError):
                strict_json(raw)
        self.assertEqual(strict_json(b'{"x":1}'), {"x": 1})

    def test_fragmented_frames_and_absolute_deadline(self):
        left, right = socket.socketpair()
        try:
            raw = b'{"x":1}'
            for value in struct.pack('!I', len(raw)) + raw:
                left.sendall(bytes([value]))
            self.assertEqual(receive(right, time.monotonic() + 1), {"x": 1})
            left.sendall(struct.pack('!I', MAX_FRAME + 1))
            with self.assertRaises(ClusterError):
                receive(right, time.monotonic() + 1)
            left.sendall(struct.pack('!I', 100) + b'{')
            with self.assertRaises((TimeoutError, ClusterError)):
                receive(right, time.monotonic() + .05)
        finally:
            left.close()
            right.close()


class ClusterTlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
        if not Path(cls.tool).is_file():
            raise unittest.SkipTest('OpenSSL test certificate generator unavailable; TLS tests blocked.')
        cls.temp = tempfile.TemporaryDirectory(prefix='spike-cluster-test-')
        cls.root = Path(cls.temp.name)
        cls.certs = {}
        for name in ('node', 'client', 'other'):
            key, cert = cls.root / f'{name}.key', cls.root / f'{name}.pem'
            subprocess.run([cls.tool, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-keyout', str(key), '-out', str(cert), '-subj', f'/CN={name}',
                            '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
                            '-addext', 'basicConstraints=critical,CA:TRUE'],
                           check=True, capture_output=True, timeout=30)
            cls.certs[name] = {'certificate': str(cert), 'private_key': str(key)}
        cls.trust = cls.root / 'clients.pem'
        cls.trust.write_bytes(Path(cls.certs['client']['certificate']).read_bytes() +
                              Path(cls.certs['other']['certificate']).read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.called = 0
        config = {**self.certs['node'], 'trust_cert': str(self.trust), 'port': 0,
                  'allowed_clients': [self.cert_pin('client')], 'max_concurrency': 2,
                  'max_threads_per_job': 1, 'max_timeout_s': 30}
        def execute(request, **kwargs):
            self.called += 1
            return run_parallel_batch(request, **kwargs)
        self.server = NodeServer(config, catalog=pool_catalog, execute=execute)
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()
        self.node = {'id': 'node-1', 'host': '127.0.0.1', 'port': self.server.port,
                     'server_name': 'localhost', 'trust_cert': self.certs['node']['certificate'],
                     'fingerprint_sha256': self.cert_pin('node')}
        self.config = {'identity': self.certs['client'], 'nodes': [self.node]}

    def tearDown(self):
        self.server.close()
        self.thread.join(timeout=2)

    def cert_pin(self, name):
        pem = Path(self.certs[name]['certificate']).read_text()
        return fingerprint(ssl.PEM_cert_to_DER_cert(pem))

    def request(self, method='catalog', batch=None):
        value = {'contract': CONTRACT, 'id': 'test', 'method': method}
        if batch is not None:
            value['batch'] = batch
        return value

    def batch(self):
        return {'contract': 'spike/parallel-batch/v1', 'jobs': [
            {'id': 'harness-a', 'method': 'run_harness_pi', 'params': {'request': fixture()}},
            {'id': 'harness-b', 'method': 'run_harness_pi', 'params': {'request': fixture()}}],
            'concurrency': 2, 'threads_per_job': 1, 'timeout_s': 30}

    def test_real_enrolled_tls_batch_and_provenance(self):
        status = probe_pool(self.config)
        self.assertEqual(status['nodes'][0]['state'], 'ready', status)
        result = run_cluster_batch(self.config, self.batch())
        self.assertEqual(result['request_sha256'], digest(self.batch()))
        self.assertTrue(all(job['ok'] for job in result['jobs']), result)
        self.assertEqual([job['id'] for job in result['jobs']], ['harness-a', 'harness-b'])
        self.assertTrue(all(job['node_certificate_sha256'] == self.cert_pin('node') for job in result['jobs']))
        self.assertEqual(self.called, 1)

    def test_wrong_pin_hostname_chain_and_no_client_certificate(self):
        for changes in ({'fingerprint_sha256': '0' * 64}, {'server_name': 'wrong.invalid'},
                        {'trust_cert': self.certs['other']['certificate']}):
            with self.assertRaises((OSError, ClusterError)):
                node_request({**self.node, **changes}, self.certs['client'], self.request())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(self.certs['node']['certificate'])
        with socket.create_connection(('127.0.0.1', self.server.port), timeout=2) as raw:
            with self.assertRaises((OSError, ClusterError)):
                with context.wrap_socket(raw, server_hostname='localhost') as sock:
                    sock.sendall(b'\0\0\0\2{}')
                    receive(sock, time.monotonic() + 2)
        self.assertEqual(self.called, 0)

    def test_chain_valid_but_unapproved_client_cannot_dispatch(self):
        try:
            reply = node_request(self.node, self.certs['other'], self.request())
        except ClusterError as exc:
            # Rejection precedes reading the request. Windows TLS/TCP may
            # discard the framed denial on close while client bytes are unread.
            # Either path must deny the unapproved identity without dispatch.
            self.assertEqual(exc.code, 'SPIKE-CLUSTER-TRANSPORT')
        else:
            self.assertFalse(reply['ok'])
            self.assertEqual(reply['error_code'], 'SPIKE-CLUSTER-TRUST')
        self.assertEqual(self.called, 0)

    def test_unsafe_methods_oversized_batch_and_node_policy_rejected(self):
        for change in ('method', 'size', 'policy'):
            batch = self.batch()
            if change == 'method':
                batch['jobs'][0]['method'] = 'run_python_script'
            elif change == 'size':
                batch['jobs'] *= 33
            else:
                batch['threads_per_job'] = 2
            reply = node_request(self.node, self.certs['client'], self.request('batch', batch))
            self.assertFalse(reply['ok'], reply)

    def test_enrollment_duplicate_nodes_and_strict_fields(self):
        path = self.root / 'pool.json'
        config = {'contract': 'spike/cluster-enrollment/v1', **copy.deepcopy(self.config)}
        path.write_text(json.dumps(config))
        self.assertEqual(load_pool(path)['nodes'][0]['id'], 'node-1')
        config['nodes'].append(config['nodes'][0])
        path.write_text(json.dumps(config))
        with self.assertRaises(ClusterError):
            load_pool(path)

    def test_result_digest_mismatch_is_unknown_and_never_replayed(self):
        original = self.server.execute
        def tampered(request, **kwargs):
            result = original(request, **kwargs)
            result['provenance']['request_sha256'] = '0' * 64
            return result
        self.server.execute = tampered
        result = run_cluster_batch(self.config, self.batch())
        self.assertTrue(all(job['state'] == 'unknown' for job in result['jobs']), result)
        self.assertEqual(self.called, 1)

    def test_bad_authenticated_result_shape_is_contained(self):
        self.server.execute = lambda *_args, **_kw: {'outcomes': [None], 'provenance': None}
        result = run_cluster_batch(self.config, self.batch())
        self.assertTrue(all(job['state'] == 'unknown' for job in result['jobs']))

    def test_result_data_tamper_with_valid_batch_hash_is_rejected(self):
        original = self.server.execute
        def tampered(request, **kwargs):
            result = original(request, **kwargs)
            result['outcomes'][0]['result'] = {'invented_temperature_k': 999}
            return result
        self.server.execute = tampered
        result = run_cluster_batch(self.config, self.batch())
        self.assertTrue(all(job['state'] == 'unknown' for job in result['jobs']))
        self.assertEqual(self.called, 1)

    def test_two_separate_tls_nodes_execute_partitioned_jobs(self):
        processes, nodes = [], []
        try:
            for index in range(2):
                with socket.socket() as reserving:
                    reserving.bind(('127.0.0.1', 0))
                    port = reserving.getsockname()[1]
                config = {**self.server.config, 'contract': 'spike/cluster-node/v1', 'port': port, 'bind': '127.0.0.1'}
                path = self.root / f'node-{index}.json'
                path.write_text(json.dumps(config))
                import sys
                processes.append(subprocess.Popen([sys.executable, '-m', 'python.spike_core.cluster_cli',
                                                   'cluster-serve', str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
                nodes.append({**self.node, 'id': f'node-{index}', 'port': port})
            config = {'identity': self.certs['client'], 'nodes': nodes}
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                status = probe_pool(config)
                if all(row['state'] == 'ready' for row in status['nodes']):
                    break
                time.sleep(.1)
            self.assertTrue(all(row['state'] == 'ready' for row in status['nodes']), status)
            result = run_cluster_batch(config, self.batch())
            self.assertTrue(all(job['ok'] for job in result['jobs']), result)
            self.assertEqual({job['node_id'] for job in result['jobs']}, {'node-0', 'node-1'})
            self.assertEqual(len({job['provenance']['worker_pid'] for job in result['jobs']}), 2)
        finally:
            for process in processes:
                process.kill()
                process.wait(timeout=5)
                process.stderr.close()

    def test_disconnect_cancels_node_work_and_releases_batch(self):
        entered, cancelled = threading.Event(), threading.Event()
        def waiting(_request, *, cancel_check):
            entered.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if cancel_check():
                    cancelled.set()
                    return {}
                time.sleep(.01)
            return {}
        self.server.execute = waiting
        from python.spike_core.cluster_protocol import send
        context = tls_context({**self.certs['client'], 'trust_cert': self.node['trust_cert']}, server=False)
        with socket.create_connection(('127.0.0.1', self.server.port), timeout=2) as raw:
            with context.wrap_socket(raw, server_hostname='localhost') as sock:
                send(sock, self.request('batch', self.batch()), time.monotonic() + 2)
                self.assertTrue(entered.wait(2))
        self.assertTrue(cancelled.wait(2))

    def test_optional_discovery_is_inert_and_bounded(self):
        from python.spike_core.cluster_discovery import DiscoveryResponder, discover
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reserve:
            reserve.bind(('127.0.0.1', 0))
            port = reserve.getsockname()[1]
        responder = DiscoveryResponder(self.server.port, port=port)
        try:
            result = discover(broadcast='127.0.0.1', port=port, timeout_s=.2)
            self.assertEqual(result['trust'], 'untrusted_hints_only')
            self.assertEqual(result['nodes'][0]['port'], self.server.port)
            self.assertEqual(self.called, 0)
        finally:
            responder.close()


if __name__ == '__main__':
    unittest.main()
