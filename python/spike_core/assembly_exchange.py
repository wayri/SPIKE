"""Portable external-CAD assembly exchange importer.

A ZIP contains assembly.json and local board/model assets. No archive member
can request host paths. Geometry and occurrence placement have separate IDs.
"""
from __future__ import annotations

import json
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from .assembly_frames import IDENTITY, validate_rigid_transform
from .design_ir_v2 import AssemblyIRV1, AssemblyPart, BoardInstance, DesignIRV2
from .design_ir_v2_schema import CoordinateFrame, canonical_uuid, content_digest
from .mcad_importer import import_mcad_artifact
from .service_project import import_design
from .project_package import _source_member_name

MAX_ASSET_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024


def read_exchange(path):
    source = Path(path)
    if source.stat().st_size > MAX_TOTAL_BYTES:
        raise ValueError("Assembly exchange exceeds 512 MiB.")
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > 256 or sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
                raise ValueError("Assembly exchange exceeds 256 members or 512 MiB expanded size.")
            names = set()
            for info in infos:
                name = info.filename
                parts = PurePosixPath(name).parts
                if name in names or not parts or name.startswith("/") or "\\" in name or ":" in name or ".." in parts:
                    raise ValueError("Assembly archive has duplicate or unsafe member paths.")
                names.add(name)
                if info.file_size > MAX_ASSET_BYTES or info.file_size > max(1, info.compress_size) * 200:
                    raise ValueError("Assembly asset exceeds size or compression-ratio limits.")
            if "assembly.json" not in names or archive.getinfo("assembly.json").file_size > 4 * 1024 * 1024:
                raise ValueError("Assembly exchange requires assembly.json (at most 4 MiB).")
            manifest = json.loads(archive.read("assembly.json"))
            if not isinstance(manifest, dict): raise ValueError("Assembly manifest must be an object.")
            if manifest.get("contract") != "spike/assembly-exchange/v1":
                raise ValueError("Unsupported assembly exchange contract.")
            if manifest.get("units", "mm") not in {"mm", "cm", "m", "inch"}:
                raise ValueError("Assembly units must be mm, cm, m, or inch.")
            occurrences = manifest.get("occurrences", [])
            if not isinstance(occurrences, list) or not 1 <= len(occurrences) <= 120:
                raise ValueError("Assembly exchange requires 1–120 occurrences.")
            if any(not isinstance(item, dict) for item in occurrences): raise ValueError("Assembly occurrences must be objects.")
            requested = {item.get("asset") for item in occurrences if item.get("asset")}
            if not requested <= names:
                raise ValueError("An assembly occurrence references a missing asset.")
            assets = {name: archive.read(name) for name in requested}
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid assembly exchange: {exc}") from exc
    return manifest, assets


def import_exchange(path, root_frame="assembly", namespace=""):
    manifest, assets = read_exchange(path)
    digest = content_digest({"manifest": manifest, "assets": {k: content_digest(v) for k, v in assets.items()}})
    namespace = namespace or digest
    identity = lambda kind, value: canonical_uuid("assembly-exchange", namespace, kind, value)
    occurrences = manifest["occurrences"]
    native_ids = [item.get("id") for item in occurrences]
    if any(not isinstance(i, str) or not i or ":" in i for i in native_ids) or len(set(native_ids)) != len(native_ids):
        raise ValueError("Occurrence IDs must be unique non-empty strings without colons.")
    scale = {"mm": 1, "cm": 10, "m": 1000, "inch": 25.4}[manifest.get("units", "mm")]
    boards, parts, designs, models, model_artifacts, source_artifacts, reports = [], [], {}, {}, {}, {}, []
    cache = {}
    with tempfile.TemporaryDirectory(prefix="spike-assembly-exchange-") as directory:
        for occurrence in occurrences:
            native = occurrence["id"]
            kind = occurrence.get("kind")
            if kind not in {"board", "part", "group"}:
                raise ValueError("Occurrence kind must be board, part, or group.")
            parent = occurrence.get("parent_id")
            if parent and parent not in native_ids:
                raise ValueError(f"Occurrence {native} has an unknown parent.")
            transform = list(validate_rigid_transform(occurrence.get("transform", IDENTITY)))
            for index in (3, 7, 11): transform[index] *= scale
            frame = CoordinateFrame(frame_id=identity("frame", native), parent_frame_id=identity("frame", parent) if parent else root_frame, transform=tuple(transform))
            name = occurrence.get("name") or native
            extensions = {"spike.assembly-exchange": {"native_id": native, "source_sha256": digest, "source_cad": manifest.get("source_cad", ""), "metadata": occurrence.get("metadata", {})}}
            asset = occurrence.get("asset")
            if kind == "group":
                parts.append(AssemblyPart(id=identity("occurrence", native), name=name, frame=frame, part_type="subassembly", extensions=extensions))
                continue
            if not asset or asset not in assets:
                raise ValueError(f"Occurrence {native} requires an embedded asset.")
            if (kind, asset) not in cache:
                local = Path(directory) / (content_digest(asset)[:16] + Path(asset).suffix)
                local.write_bytes(assets[asset])
                if kind == "board":
                    if local.suffix.lower() == ".json":
                        design = DesignIRV2.from_dict(json.loads(assets[asset])).to_dict()
                        report = {"source_format": "spike/design-ir/v2", "source_sha256": content_digest(assets[asset])}
                    else:
                        outcome = import_design(str(local), with_report=True)
                        design, report = outcome["design"], outcome["report"]
                        # The importer reads a temporary extraction path. Bind
                        # retained provenance to the exact embedded bytes.
                        source_digest = content_digest(assets[asset])
                        if design["source"]["source_digest"] != source_digest:
                            raise ValueError("Assembly board source identity changed during import.")
                        design["source"]["artifact_path"] = "package:" + _source_member_name(Path(asset).name, source_digest)
                    cache[(kind, asset)] = design
                    designs[design["design_id"]] = design
                    source_artifacts[content_digest(assets[asset])[:16] + "-" + Path(asset).name] = assets[asset]
                    reports.append(report)
                else:
                    outcome = import_mcad_artifact(local)
                    cache[(kind, asset)] = outcome
                    models[outcome.model.id] = asdict(outcome.model)
                    model_artifacts[outcome.artifact_name] = outcome.artifact_bytes
                    reports.append(outcome.report.to_dict())
            if kind == "board":
                boards.append(BoardInstance(id=identity("occurrence", native), name=name, frame=frame, design_id=cache[(kind, asset)]["design_id"], extensions=extensions))
            else:
                outcome = cache[(kind, asset)]
                parts.append(AssemblyPart(id=identity("occurrence", native), name=name, frame=frame,
                    part_type=occurrence.get("part_type", "enclosure"), model_id=outcome.model.id, extensions={**outcome.part.extensions, **extensions}))
    assembly = AssemblyIRV1(assembly_id=identity("assembly", manifest.get("name", "Imported assembly")), name=manifest.get("name", "Imported assembly"), frame=CoordinateFrame(frame_id=root_frame), boards=boards, parts=parts)
    # Connector/harness endpoints use source occurrence IDs and are remapped.
    raw = assembly.to_dict()
    for mapping in manifest.get("connector_mappings", []):
        data = dict(mapping["data"])
        if data.get("board_id") not in native_ids:
            raise ValueError("Connector mapping has unknown source board ID.")
        data["board_id"] = identity("occurrence", data["board_id"])
        data["position_mm"] = [float(v) * scale for v in data["position_mm"]]
        raw["connector_mappings"].append({**mapping, "id": identity("connector", mapping["id"]), "data": data})
    for harness in manifest.get("harnesses", []):
        item = dict(harness)
        item["id"] = identity("harness", item["id"])
        for key in ("endpoint_a", "endpoint_b"):
            board, connector = item[key].split("::", 1)
            if board not in native_ids: raise ValueError("Harness references an unknown source board.")
            item[key] = identity("occurrence", board) + "::" + connector
        item["length_mm"] = float(item.get("length_mm", 0)) * scale
        raw["harnesses"].append(item)
    assembly = AssemblyIRV1.from_dict(raw)
    return {"assembly": assembly.to_dict(), "designs": designs, "models": list(models.values()), "model_artifacts": model_artifacts,
            "source_artifacts": source_artifacts, "reports": reports, "source_sha256": digest}
