"""Bounded named-solid MCAD export through the optional FreeCAD runtime."""
from __future__ import annotations
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

from .mcad_export_contract import MAX_BYTES, validate_assembly
from .mcad_importer import validate_step_mcad_artifact
from .mcad_tessellation import _freecad_path
from .sparselizard_process import run_adapter_process


def export_assembly(assembly, *, freecad_executable=None, cancellation_event=None):
    """Return a STEP artifact and a complete STEP/FCStd/BREP/metadata ZIP.

    No caller-selected path is written. The desktop asks where to save the
    returned bytes. Input assets are embedded and digest checked, never fetched.
    """
    document = validate_assembly(assembly)
    executable = _freecad_path(freecad_executable)
    with tempfile.TemporaryDirectory(prefix="spike-mcad-export-") as folder:
        root = Path(folder)
        encoded = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
        (root / "assembly.json").write_bytes(encoded)
        (root / "export.py").write_bytes(Path(__file__).with_name("freecad_assembly_export.py").read_bytes())
        stdin = ("scope={'__name__':'spike_mcad_export'}\n"
                 "exec(compile(open('export.py',encoding='utf-8').read(),'export.py','exec'),scope)\n"
                 "scope['export']('.')\nraise SystemExit(0)\n").encode()
        result = run_adapter_process(
            [str(executable), "--console", "--user-cfg", str(root / "user.cfg"), "--system-cfg", str(root / "system.cfg")],
            cwd=root, timeout_s=300, memory_limit_mb=4096, output_limit_bytes=MAX_BYTES,
            stream_limit_bytes=1024**2, stdin_payload=stdin, cancellation_event=cancellation_event)
        manifest_path = root / "manifest.json"
        if result["return_code"] or not manifest_path.is_file():
            detail = str(result.get("stderr", "")) + str(result.get("stdout", ""))
            raise RuntimeError("MCAD export failed; no artifact accepted: " + detail[-5000:])
        paths = [root / "assembly.step", root / "assembly.FCStd", manifest_path]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("contract") != "spike/mcad-export-manifest/v1":
            raise ValueError("Invalid MCAD exporter manifest.")
        expected = {o["id"] for o in document["objects"]}
        records = manifest.get("objects", [])
        if {o["id"] for o in records} != expected or len(records) != len(expected):
            raise ValueError("MCAD exporter changed object identities.")
        for record in records:
            if record["kind"] == "assembly":
                continue
            if record.get("step_roundtrip") != "passed":
                raise ValueError("MCAD exporter did not verify every solid.")
            name = record.get("brep_file", "")
            if Path(name).name != name or not name.endswith(".brep"):
                raise ValueError("Invalid BREP artifact path.")
            paths.append(root / name)
        if any(not p.is_file() or p.stat().st_size <= 0 for p in paths):
            raise ValueError("MCAD export artifact missing or empty.")
        if sum(p.stat().st_size for p in paths) + len(encoded) > MAX_BYTES:
            raise ValueError("MCAD export exceeds the 64 MiB combined artifact budget.")
        step = paths[0].read_bytes()
        validate_step_mcad_artifact(step)
        manifest["input_sha256"] = hashlib.sha256(encoded).hexdigest()
        manifest["artifacts"] = [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                                 for p in paths if p != manifest_path]
        manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False)
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                if path != manifest_path:
                    archive.writestr(path.name, path.read_bytes())
            archive.writestr("manifest.json", manifest_text)
            archive.writestr("assembly.spike-mcad.json", encoded)
        return {"contract": "spike/mcad-export/v1", "manifest": manifest,
                "artifacts": [
                    {"file_name": "assembly.step", "media_type": "model/step", "encoding": "base64", "data": base64.b64encode(step).decode(), "sha256": hashlib.sha256(step).hexdigest()},
                    {"file_name": "assembly-mcad.zip", "media_type": "application/zip", "encoding": "base64", "data": base64.b64encode(bundle.getvalue()).decode(), "sha256": hashlib.sha256(bundle.getvalue()).hexdigest()},
                    {"file_name": "assembly-manifest.json", "media_type": "application/json", "encoding": "utf-8", "data": manifest_text, "sha256": hashlib.sha256(manifest_text.encode()).hexdigest()},
                ]}
