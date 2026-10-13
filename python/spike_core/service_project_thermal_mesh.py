# SPDX-License-Identifier: Apache-2.0
"""Bounded project-owned thermal meshing; no imported filesystem paths."""
from __future__ import annotations

import copy
import json
import tempfile
import zipfile
from pathlib import Path

from .project_package import ProjectPackageError, _safe_member_path, _verify_member_stream, write_spike_package
from .service_project_assembly_field import _open_current_project, _assembly_identity
from .service_helpers import error_response, operation_id

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
IDENTITY_KEYS = {"project_path", "expected_manifest_payload_sha256"}


def _artifact_reader(path, opened):
    records = {item["path"]: item for item in opened.manifest["members"]}

    def read(uri):
        if not isinstance(uri, str) or not uri.startswith("package:"):
            raise ProjectPackageError("THERMAL_SOURCE: retain the source inside the SPIKE package.")
        member = _safe_member_path(uri[len("package:"):])
        record = records.get(member)
        if record is None:
            raise ProjectPackageError("THERMAL_SOURCE: artifact is absent from the verified manifest.")
        size = record["size"]
        if type(size) is not int or not 0 < size <= MAX_ARTIFACT_BYTES:
            raise ProjectPackageError("THERMAL_SOURCE_BUDGET: artifact exceeds 64 MiB.")
        with zipfile.ZipFile(path) as archive:
            # Detect replacement between project validation and targeted reads.
            if json.loads(archive.read("manifest.json")) != opened.manifest:
                raise ProjectPackageError("THERMAL_PROJECT_STALE: reopen the changed project.")
            info = archive.getinfo(member)
            if info.file_size != size or info.file_size > MAX_ARTIFACT_BYTES:
                raise ProjectPackageError("THERMAL_SOURCE_BUDGET: manifest size mismatch.")
            return _verify_member_stream(archive, info, expected_size=size,
                                        expected_sha256=record["sha256"], retain=True)
    return read


def read_assembly_thermal_mesh_setup(params):
    if set(params) != IDENTITY_KEYS:
        raise ProjectPackageError("Thermal mesh inventory requires exact project and manifest identities.")
    _, opened = _open_current_project(params, "reviewing thermal volumes", include_members=False)
    assembly, _ = _assembly_identity(opened.payload.get("assembly_ir"))
    designs = {d["design_id"]: d for d in (opened.payload.get("assembly_designs") or {}).get("designs", [])}
    active = opened.payload.get("design_ir")
    if active:
        designs.setdefault(active["design_id"], active)
    board_ids = {board["design_id"] for board in assembly.get("boards", [])}
    boards = []
    for did in sorted(board_ids):
        design = designs.get(did, {})
        layers = [layer for layer in design.get("layers", []) if
                  layer.get("layer_type") in ("copper", "dielectric", "soldermask", "solder_mask", "paste")
                  or layer.get("extensions", {}).get("spike.v1.stackup")]
        boards.append({"design_id": did, "name": design.get("name", did), "layers": layers})
    from .assembly_thermal_components import thermal_component_inventory, PROVENANCE_KEY, MATERIALS_KEY
    return {"assembly": assembly, "boards": boards,
            "parts": [part for part in assembly.get("parts", []) if part.get("model_id")
                      or part.get("part_type") != "subassembly"],
            "components": thermal_component_inventory(opened.payload),
            "thermal_materials": list(assembly.get('extensions', {}).get(MATERIALS_KEY, {}).values()),
            "part_material_assignments": {part['id']: part['material_id'] for part in assembly.get('parts', [])
                                           if PROVENANCE_KEY in part.get('extensions', {}) or 'spike.v1.encapsulation' in part.get('extensions', {})},
            "model_status": "experimental"}


def promote_thermal_components_in_project(params, *, application_version=''):
    if not isinstance(params, dict) or set(params) != IDENTITY_KEYS | {'selections', 'materials'}:
        raise ProjectPackageError('Component promotion requires project identity, explicit selections and reviewed materials.')
    from .assembly_field_handoff import bounded_json
    from .assembly_thermal_components import promote_thermal_components
    from .service_project_assembly import _invalidate_saved_results
    bounded_json(params)
    path, opened = _open_current_project(params, 'promoting retained STEP components', include_members=True)
    before = copy.deepcopy(opened.payload.get('assembly_ir'))
    proposed = promote_thermal_components(opened.payload, params['selections'], params['materials'],
                                         artifact_reader=_artifact_reader(path, opened))
    payload, invalidated = _invalidate_saved_results(proposed['payload'], before)
    audit = payload.setdefault('audit', [])
    if not isinstance(audit, list):
        raise ProjectPackageError('Project audit must be an array.')
    audit.append({'event': 'thermal_components_promoted',
                  'part_ids': [part['id'] for part in proposed['promoted_parts']],
                  'placement_reviewed': True, 'contacts_inferred': False})
    _open_current_project(params, 'committing retained thermal components', include_members=False)
    manifest = write_spike_package(path, payload, preserved_members=opened.members,
                                  profile=str(opened.manifest.get('profile', 'portable_project')),
                                  application_version=application_version)
    return {'manifest': manifest, 'assembly': payload['assembly_ir'],
            'promoted_parts': proposed['promoted_parts'],
            'part_material_assignments': proposed['part_material_assignments'],
            'materials': proposed['materials'], 'invalidated_results': invalidated,
            'contacts_inferred': False, 'model_status': 'experimental'}


def run_assembly_thermal_mesh_in_project(params, *, application_version=None):
    if application_version is None:
        from . import __version__
        application_version = __version__
    if set(params) != IDENTITY_KEYS | {"assignments", "mesh_options"}:
        raise ProjectPackageError("Thermal meshing requires exact project identities, assignments and mesh options.")
    path, opened = _open_current_project(params, "generating thermal volumes", include_members=True)
    payload = copy.deepcopy(opened.payload)
    payload["assembly_ir"], _ = _assembly_identity(payload.get("assembly_ir"))
    from .assembly_thermal_meshing import run_assembly_thermal_mesh
    with tempfile.TemporaryDirectory(prefix="spike-thermal-mesh-") as directory:
        result = run_assembly_thermal_mesh(payload, params["assignments"], params["mesh_options"],
                                          Path(directory) / "volumes", artifact_reader=_artifact_reader(path, opened))
        if len(json.dumps(result, allow_nan=False).encode('utf-8')) > 32 * 1024**2:
            raise ProjectPackageError('THERMAL_MESH_BUDGET: generated handoff exceeds 32 MiB; use a coarser mesh')
        if result.get('status') == 'completed' and result.get('encapsulation_sources'):
            from .service_project_encapsulation import retain_generated_encapsulation
            result = retain_generated_encapsulation(params, opened, path, result, Path(directory) / 'volumes',
                                                   application_version=application_version)
            return result
    _open_current_project(params, "accepting generated thermal volumes", include_members=False)
    # Control-plane IPC has an explicit bounded payload contract.
    if len(json.dumps(result, allow_nan=False).encode("utf-8")) > 32 * 1024 * 1024:
        raise ProjectPackageError("THERMAL_MESH_BUDGET: generated handoff exceeds 32 MiB; use a coarser mesh.")
    return result


def handle_thermal_mesh_project_request(method, params, *, request_id, application_version):
    if method == 'promote_thermal_components_in_project':
        try:
            return {'ok': True, 'result': promote_thermal_components_in_project(params, application_version=application_version)}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, zipfile.BadZipFile) as exc:
            return error_response('SPIKE-BE-THERMAL-E-0003', str(exc), error_type=type(exc).__name__,
                                  operation_id=operation_id(request_id))
    operation = {"read_assembly_thermal_mesh_setup": read_assembly_thermal_mesh_setup,
                 "run_assembly_thermal_mesh_in_project": run_assembly_thermal_mesh_in_project}.get(method)
    if operation is None:
        return None
    try:
        return {"ok": True, "result": operation(params, application_version=application_version) if method == 'run_assembly_thermal_mesh_in_project' else operation(params)}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, zipfile.BadZipFile) as exc:
        return error_response("SPIKE-BE-THERMAL-E-0003", str(exc), error_type=type(exc).__name__,
                              operation_id=operation_id(request_id))
