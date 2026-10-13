# SPDX-License-Identifier: Apache-2.0
"""Fixed local staging contract for the optional source-tree SPIKES Studio."""
from __future__ import annotations
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

def _runtime():
    source=Path(__file__).resolve().parents[2]/"standalone"/"spikes_project"/"studio"/"python"
    if not source.is_dir(): raise RuntimeError("SPIKES Studio runtime is unavailable in this installation")
    if str(source) not in sys.path: sys.path.insert(0,str(source))
    from spikes_studio.document import write_json
    from spikes_studio.studio_handoff import validate_handoff
    return write_json,validate_handoff

def prepare_spikes_studio_handoff(payload, workspace_root):
    write_json,validate_handoff=_runtime();value=validate_handoff(payload);root=Path(workspace_root).resolve()/".local"/"studio-handoff";root.mkdir(parents=True,exist_ok=True)
    if root.resolve()!=root: raise ValueError("Studio handoff directory must not redirect outside the workspace")
    source=value["source_design"];suffix=hashlib.sha256(source["occurrence_id"].encode()).hexdigest()[:12]
    path=root/f"{source['digest']}-{suffix}.json";write_json(path,value);return path

def spikes_studio_launch_arguments(path, workspace_root):
    root=Path(workspace_root).resolve()/".local"/"studio-handoff";path=Path(path).resolve(strict=True)
    if not path.is_relative_to(root) or path.suffix.lower() != ".json": raise ValueError("Studio handoff path is outside the workspace handoff directory")
    return ("--board-circuit-handoff",str(path))

def handle_prepare_spikes_studio_handoff(params, workspace_root):
    path=prepare_spikes_studio_handoff(params["request"],workspace_root)
    return {"status":"ready","handoff_path":str(path),"launch_args":["--board-circuit-handoff",str(path)]}

def handle_launch_spikes_studio(params, workspace_root):
    path=prepare_spikes_studio_handoff(params["request"],workspace_root)
    if importlib.util.find_spec("wx") is None:
        return {"status":"unavailable","path":str(path),"message":"SPIKES Studio requires the optional wxPython runtime"}
    repository = Path(__file__).resolve().parents[2]
    launcher = repository / "scripts" / "launch_spikes_studio.py"
    if getattr(sys, "frozen", False) or not launcher.is_file():
        return {"status":"unavailable", "path":str(path), "message":"This installation does not include a runnable SPIKES Studio application"}
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    process = subprocess.Popen([sys.executable, str(launcher), *spikes_studio_launch_arguments(path, workspace_root)],
        cwd=repository, creationflags=flags, close_fds=True)
    return {"status":"launched", "path":str(path), "message":f"Started SPIKES Studio (process {process.pid})"}


def handle_studio_bridge_request(method, params, workspace_root):
    """Return a standard worker response for fixed Studio actions only."""
    if method not in {"prepare_spikes_studio_handoff", "launch_spikes_studio"}:
        return None
    from .service_helpers import error_response
    try:
        if not isinstance(params, dict) or set(params) != {"request"}:
            raise ValueError("Studio handoff requires only the bounded request graph")
        operation = handle_prepare_spikes_studio_handoff if method.startswith("prepare_") else handle_launch_spikes_studio
        return {"ok": True, "result": operation(params, workspace_root)}
    except (ImportError, KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", str(exc), error_type=type(exc).__name__, context={"method": method})
