"""Discovery and integrity checks for the native sparseLizard runtime bundle."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable


RUNTIME_CONTRACTS = frozenset({
    "spike/sparselizard-native-runtime/v1",
    "spike/sparselizard-native-runtime/v2",
})
SELF_TEST_CONTRACT = "spike/sparselizard-runtime-self-test/v1"


def _app_root() -> Path:
    configured = os.environ.get("SPIKE_HOME", "").strip()
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2]


def _candidate_roots() -> Iterable[Path]:
    configured = os.environ.get("SPIKE_SPARSELIZARD_RUNTIME", "").strip()
    if configured:
        yield Path(configured).expanduser()
        return
    yield _app_root() / "runtime" / "external" / "sparselizard" / "native-windows"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=8)
def _detached_signature_valid(content: str, signature: str, content_mtime_ns: int, signature_mtime_ns: int) -> bool:
    """Verify a detached CMS signature without loading solver code in-process."""

    del content_mtime_ns, signature_mtime_ns
    content_path = Path(content)
    signature_path = Path(signature)
    try:
        if os.name == "nt":
            powershell = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            command = [
                str(powershell), "-NoProfile", "-NonInteractive", "-Command",
                "$c=[IO.File]::ReadAllBytes($args[0]);$s=[IO.File]::ReadAllBytes($args[1]);"
                "$m=[Security.Cryptography.Pkcs.SignedCms]::new([Security.Cryptography.Pkcs.ContentInfo]::new($c),$true);"
                "$m.Decode($s);$m.CheckSignature($true)",
                str(content_path), str(signature_path),
            ]
        else:
            openssl = shutil.which("openssl")
            if not openssl:
                return False
            command = [
                openssl, "cms", "-verify", "-binary", "-inform", "DER",
                "-content", str(content_path), "-in", str(signature_path),
                "-noverify", "-out", os.devnull,
            ]
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=10, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def detect_sparselizard_runtime() -> Dict[str, Any]:
    """Return a verified runtime state without enabling PCB solver capabilities."""

    for candidate in _candidate_roots():
        try:
            root = candidate.resolve(strict=True)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            contract = str(manifest.get("contract", ""))
            if contract not in RUNTIME_CONTRACTS:
                continue
            if contract.endswith("/v2"):
                signature_path = manifest_path.with_suffix(manifest_path.suffix + ".p7s")
                if not signature_path.is_file() or not _detached_signature_valid(
                    str(manifest_path), str(signature_path),
                    manifest_path.stat().st_mtime_ns, signature_path.stat().st_mtime_ns,
                ):
                    continue
            executable = (root / str(manifest.get("executable", ""))).resolve(strict=True)
            if executable.parent != (root / "bin").resolve() or executable.name != "spike-sparselizard-runtime.exe":
                continue
            expected_hash = str(manifest.get("executable_sha256", "")).lower()
            if len(expected_hash) != 64 or _sha256(executable) != expected_hash:
                continue
            self_test_path = root / str(manifest.get("self_test", {}).get("path", ""))
            self_test = json.loads(self_test_path.read_text(encoding="utf-8-sig"))
            if self_test.get("contract") != SELF_TEST_CONTRACT or self_test.get("status") != "passed":
                continue
            return {
                "available": True,
                "root": str(root),
                "executable": str(executable),
                "manifest": manifest,
                "self_test": self_test,
                "signature_verified": contract.endswith("/v2"),
                "reason": (
                    "Signed native sparseLizard runtime passed its bounded self-test."
                    if contract.endswith("/v2") else
                    "Legacy native sparseLizard runtime passed its bounded DC FEM integrity test."
                ),
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return {
        "available": False,
        "root": "",
        "executable": "",
        "manifest": {},
        "self_test": {},
        "signature_verified": False,
        "reason": "No integrity-verified native sparseLizard runtime bundle is installed.",
    }
