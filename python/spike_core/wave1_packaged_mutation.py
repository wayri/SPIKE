"""Extracted-worker mutation/reopen evidence for Wave 1 packaged acceptance."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping

from .assembly_frames import multiply, resolve_world
from .design_ir_v2 import AssemblyIRV1
from .project_package import read_project


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Wave1MutationAcceptanceError(ValueError):
    """Raised when the extracted worker violates the mutation probe contract."""


def _check(passed: bool, detail: str, **evidence: Any) -> Dict[str, Any]:
    return {
        "id": "worker.fixture_mutation_reopen",
        "status": "passed" if passed else "failed",
        "detail": detail,
        "evidence": evidence,
    }


def _invoke_worker_request(
    executable: Path, *, cwd: Path, method: str, params: Mapping[str, Any], timeout: int = 120,
) -> Dict[str, Any]:
    request = json.dumps({"id": f"wave1-{method}", "method": method, "params": dict(params)}) + "\n"
    completed = subprocess.run(
        [str(executable)], cwd=str(cwd), input=request, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        response = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as error:
        raise Wave1MutationAcceptanceError(f"Packaged worker {method} returned invalid JSON.") from error
    if completed.returncode != 0 or not isinstance(response, Mapping) or response.get("ok") is not True:
        detail = response.get("error") if isinstance(response, Mapping) else None
        raise Wave1MutationAcceptanceError(f"Packaged worker {method} failed: {detail or completed.stderr[-500:]}")
    result = response.get("result")
    if not isinstance(result, Mapping):
        raise Wave1MutationAcceptanceError(f"Packaged worker {method} omitted its result object.")
    return dict(result)


def _artifact_ledger(opened: Any) -> Dict[str, str]:
    prefixes = ("models/artifacts/", "geometry/package-shapes/")
    return {
        name: hashlib.sha256(data).hexdigest()
        for name, data in opened.members.items()
        if name.startswith(prefixes)
    }


def _claims_solver_ready(value: Any) -> bool:
    if isinstance(value, Mapping):
        return value.get("solver_ready") is True or any(_claims_solver_ready(item) for item in value.values())
    if isinstance(value, list):
        return any(_claims_solver_ready(item) for item in value)
    return False


def probe_packaged_worker_mutation_roundtrip(
    executable: str | Path, *, cwd: str | Path, fixture: str | Path,
) -> Dict[str, Any]:
    """Mutate only a temporary fixture copy through the extracted worker and reopen it."""

    path = Path(executable).resolve()
    working_directory = Path(cwd).resolve()
    source = Path(fixture).resolve()
    try:
        with tempfile.TemporaryDirectory(prefix="spike-wave1-packaged-mutation-") as directory:
            project = Path(directory) / source.name
            shutil.copy2(source, project)
            before = read_project(project, include_members=True)
            assembly = AssemblyIRV1.from_dict(before.payload["assembly_ir"])
            root_frame_id = assembly.frame.frame_id
            part = next((item for item in assembly.parts if (item.frame.parent_frame_id or root_frame_id) == root_frame_id), None)
            target = next((item.frame.frame_id for item in assembly.boards if item.frame.frame_id != part.frame.parent_frame_id), None) if part else None
            if part is None or target is None:
                raise Wave1MutationAcceptanceError("The packaged acceptance fixture lacks a root MCAD part or board reparent target.")

            before_artifacts = _artifact_ledger(before)
            old_transform = tuple(float(item) for item in part.frame.transform)
            translation_step = part.placement_policy.translation_snap_mm if part.placement_policy and part.placement_policy.translation_snap_mm else 1.0
            rotation_step = part.placement_policy.rotation_snap_deg if part.placement_policy and part.placement_policy.rotation_snap_deg else 15.0
            radians = math.radians(rotation_step)
            cosine, sine = math.cos(radians), math.sin(radians)
            rotation = (cosine, -sine, 0.0, 0.0, sine, cosine, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
            requested_transform = list(multiply(old_transform, rotation))
            requested_transform[3] += translation_step
            requested_frame = {
                "frame_id": part.frame.frame_id, "parent_frame_id": part.frame.parent_frame_id,
                "units": "mm", "handedness": "right", "transform": requested_transform,
            }
            initial_identity = str(before.manifest.get("manifest_payload_sha256", ""))
            updated = _invoke_worker_request(path, cwd=working_directory, method="update_mcad_part_in_project", params={
                "project_path": str(project), "expected_manifest_payload_sha256": initial_identity,
                "part_id": part.id, "frame": requested_frame, "name": part.name,
                "part_type": part.part_type, "material_id": part.material_id,
                "visual": {"visible": True, "opacity": 0.625},
            })
            update_manifest = updated.get("manifest") if isinstance(updated.get("manifest"), Mapping) else {}
            update_identity = str(update_manifest.get("manifest_payload_sha256", ""))
            after_update = read_project(project, include_members=True)
            updated_assembly = AssemblyIRV1.from_dict(after_update.payload["assembly_ir"])
            updated_part = next(item for item in updated_assembly.parts if item.id == part.id)
            world_after_update = resolve_world(updated_assembly, updated_part.frame)

            reparented = _invoke_worker_request(path, cwd=working_directory, method="reparent_mcad_part_in_project", params={
                "project_path": str(project), "expected_manifest_payload_sha256": update_identity,
                "part_id": part.id, "new_parent_frame_id": target,
            })
            reparent_manifest = reparented.get("manifest") if isinstance(reparented.get("manifest"), Mapping) else {}
            final_identity = str(reparent_manifest.get("manifest_payload_sha256", ""))
            worker_reopen = _invoke_worker_request(
                path, cwd=working_directory, method="read_project_package", params={"path": str(project)},
            )
            reopened = read_project(project, include_members=True)
            reopened_again = read_project(project, include_members=True)
            final_assembly = AssemblyIRV1.from_dict(reopened.payload["assembly_ir"])
            final_part = next(item for item in final_assembly.parts if item.id == part.id)
            final_world = resolve_world(final_assembly, final_part.frame)
            final_visual = final_part.extensions.get("spike.visual") if isinstance(final_part.extensions, Mapping) else None
            worker_manifest = worker_reopen.get("manifest") if isinstance(worker_reopen.get("manifest"), Mapping) else {}
            artifact_unchanged = bool(before_artifacts) and before_artifacts == _artifact_ledger(reopened)
            identities_chained = (
                all(_SHA256.fullmatch(identity) is not None for identity in (initial_identity, update_identity, final_identity))
                and len({initial_identity, update_identity, final_identity}) == 3
                and str(after_update.manifest.get("manifest_payload_sha256", "")) == update_identity
                and str(reopened.manifest.get("manifest_payload_sha256", "")) == final_identity
                and str(worker_manifest.get("manifest_payload_sha256", "")) == final_identity
            )
            world_preserved = all(abs(left - right) <= 1e-9 for left, right in zip(world_after_update, final_world))
            manifest_repeat = reopened.manifest == reopened_again.manifest
            payload_repeat = reopened.payload == reopened_again.payload
            artifact_repeat = _artifact_ledger(reopened) == _artifact_ledger(reopened_again)
            worker_canonical_matches = json.dumps(
                worker_reopen.get("canonical"), sort_keys=True, separators=(",", ":"), allow_nan=False,
            ) == json.dumps(reopened.payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
            deterministic_reopen = manifest_repeat and payload_repeat and artifact_repeat and worker_canonical_matches
            passed = (
                identities_chained and final_part.frame.parent_frame_id == target
                and final_visual == {"visible": True, "opacity": 0.625}
                and tuple(updated_part.frame.transform) == tuple(requested_transform)
                and world_preserved and artifact_unchanged and deterministic_reopen
                and not _claims_solver_ready({
                    "assembly_ir": reopened.payload.get("assembly_ir"),
                    "models": reopened.payload.get("models"),
                    "assembly_package_shapes": reopened.payload.get("assembly_package_shapes"),
                })
            )
            return _check(
                passed,
                "The extracted worker must transactionally persist snapped placement, appearance, and world-preserving reparenting on a temporary fixture copy.",
                part_id=part.id, target_frame_id=target, manifest_chain_verified=identities_chained,
                world_pose_preserved=world_preserved, artifacts_unchanged=artifact_unchanged,
                deterministic_reopen=deterministic_reopen, manifest_repeat=manifest_repeat,
                payload_repeat=payload_repeat, artifact_repeat=artifact_repeat,
                worker_canonical_matches=worker_canonical_matches, solver_ready=False,
            )
    except (OSError, ValueError, TypeError, KeyError, StopIteration, Wave1MutationAcceptanceError) as error:
        return _check(False, "The extracted-worker MCAD mutation and deterministic reopen probe failed.", error=str(error))
