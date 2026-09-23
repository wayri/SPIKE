from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from python.spikes.compiled_blocks import (
    CompiledBlockApproval,
    CompiledBlockError,
    CompiledBlockExecutionError,
    CompiledBlockManifest,
    CompiledBlockProcessRuntime,
    CompiledBlockRequest,
    CompiledBlockRuntimeLimits,
)


def _program(body: str) -> str:
    return (
        "import json,sys; r=json.loads(sys.stdin.readline()); "
        f"{body}"
    )


def _manifest(code: str, *, outputs=("duty",), state=("acc",)) -> CompiledBlockManifest:
    return CompiledBlockManifest.create(
        block_id="test.controller", version="1", implementation_language="other",
        executable=sys.executable, arguments=("-c", code), input_ports=("error",),
        output_ports=outputs, state_variables=state,
        capabilities=("control", "stateful", "discrete-time"),
    )


def _approval(manifest: CompiledBlockManifest) -> CompiledBlockApproval:
    return CompiledBlockApproval(
        manifest_sha256=manifest.manifest_sha256,
        executable_sha256=manifest.executable_sha256,
        evidence_sha256=hashlib.sha256(b"review evidence").hexdigest(),
        reviewer="test-reviewer", approved=True,
    )


def _request() -> CompiledBlockRequest:
    return CompiledBlockRequest(
        request_id="step-1", time_s=0.0, step_s=1e-6,
        ports={"error": 0.25}, state={"acc": 1.0},
    )


class CompiledBlockTests(unittest.TestCase):
    def test_exactly_approved_json_block_executes(self) -> None:
        code = _program(
            "a=r['state']['acc']+r['ports']['error']; "
            "o={'contract':'spikes/compiled-block-response/v1','request_id':r['request_id'],"
            "'ports':{'duty':a},'state':{'acc':a}}; print(json.dumps(o))"
        )
        manifest = _manifest(code)
        response = CompiledBlockProcessRuntime([_approval(manifest)]).execute(
            manifest, sys.executable, _request(),
        )
        self.assertEqual(dict(response.ports), {"duty": 1.25})
        self.assertEqual(dict(response.state), {"acc": 1.25})

    def test_manifest_is_content_addressed_and_approval_is_fail_closed(self) -> None:
        code = _program(
            "print(json.dumps({'contract':'spikes/compiled-block-response/v1',"
            "'request_id':r['request_id'],'ports':{'duty':0.0},'state':{'acc':0.0}}))"
        )
        manifest = _manifest(code)
        with self.assertRaisesRegex(CompiledBlockError, "manifest_sha256"):
            replace(manifest, arguments=("-c", "print('changed')"))
        with self.assertRaisesRegex(CompiledBlockError, "explicit"):
            replace(_approval(manifest), approved=False)
        with self.assertRaisesRegex(CompiledBlockExecutionError, "execution_not_approved"):
            CompiledBlockProcessRuntime([]).execute(manifest, sys.executable, _request())

    def test_executable_digest_and_schema_are_exact(self) -> None:
        code = _program(
            "print(json.dumps({'contract':'spikes/compiled-block-response/v1',"
            "'request_id':r['request_id'],'ports':{'wrong':0.0},'state':{'acc':0.0}}))"
        )
        manifest = _manifest(code)
        runtime = CompiledBlockProcessRuntime([_approval(manifest)])
        with self.assertRaisesRegex(CompiledBlockExecutionError, "response_schema_mismatch"):
            runtime.execute(manifest, sys.executable, _request())
        with tempfile.TemporaryDirectory() as directory:
            counterfeit = Path(directory) / Path(sys.executable).name
            counterfeit.write_bytes(b"not the approved executable")
            with self.assertRaisesRegex(CompiledBlockExecutionError, "executable_identity_mismatch"):
                runtime.execute(manifest, counterfeit, _request())

    def test_nonfinite_duplicate_and_extra_response_data_are_rejected(self) -> None:
        cases = (
            ("print('{\"contract\":\"spikes/compiled-block-response/v1\",\"contract\":\"x\"}')", "invalid_json_response"),
            (
                "print(json.dumps({'contract':'spikes/compiled-block-response/v1',"
                "'request_id':r['request_id'],'ports':{'duty':float('nan')},'state':{'acc':0.0}}))",
                "invalid_json_response",
            ),
            (
                "print(json.dumps({'contract':'spikes/compiled-block-response/v1',"
                "'request_id':r['request_id'],'ports':{'duty':0.0},'state':{'acc':0.0},'extra':1}))",
                "invalid_response_schema",
            ),
        )
        for body, error in cases:
            with self.subTest(error=error):
                manifest = _manifest(_program(body))
                with self.assertRaisesRegex(CompiledBlockExecutionError, error):
                    CompiledBlockProcessRuntime([_approval(manifest)]).execute(
                        manifest, sys.executable, _request(),
                    )

    def test_timeout_and_combined_output_cap_are_enforced(self) -> None:
        timeout_manifest = _manifest(_program("import time; time.sleep(2)"))
        with self.assertRaisesRegex(CompiledBlockExecutionError, "process_timeout"):
            CompiledBlockProcessRuntime(
                [_approval(timeout_manifest)], CompiledBlockRuntimeLimits(timeout_s=0.05),
            ).execute(timeout_manifest, sys.executable, _request())

        output_manifest = _manifest(_program("print('x'*4096)"))
        with self.assertRaisesRegex(CompiledBlockExecutionError, "output_limit_exceeded"):
            CompiledBlockProcessRuntime(
                [_approval(output_manifest)], CompiledBlockRuntimeLimits(max_output_bytes=128),
            ).execute(output_manifest, sys.executable, _request())

    def test_request_ports_state_and_finite_numbers_are_bounded(self) -> None:
        with self.assertRaisesRegex(CompiledBlockError, "finite"):
            replace(_request(), ports={"error": float("inf")})
        code = _program("print('{}')")
        manifest = _manifest(code)
        runtime = CompiledBlockProcessRuntime([_approval(manifest)])
        with self.assertRaisesRegex(CompiledBlockExecutionError, "request_schema_mismatch"):
            runtime.execute(manifest, sys.executable, replace(_request(), ports={"other": 1.0}))


if __name__ == "__main__":
    unittest.main()
