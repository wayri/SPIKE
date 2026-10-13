# SPDX-License-Identifier: Apache-2.0
"""Installed, offline-only contract discovery and validation."""
from __future__ import annotations
import json
import hashlib
import itertools
import sys
from pathlib import Path
from typing import Any

MAX_SCHEMA_BYTES = 1024 * 1024
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024

def installed_schema_catalog() -> dict[str, Path]:
    roots = [Path(getattr(sys, "_MEIPASS", "")) / "schemas"] if getattr(sys, "frozen", False) else []
    roots.append(Path(__file__).resolve().parents[2] / "schemas")
    directory = next((root.resolve() for root in roots if root.is_dir()), None)
    if directory is None:
        raise RuntimeError("Installed SPIKE contract schemas are unavailable")
    return {path.name: path for path in directory.glob("*.schema.json") if path.is_file() and not path.is_symlink()}

def _read_schema(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.stat().st_size > MAX_SCHEMA_BYTES:
        raise ValueError("Installed schema exceeds the 1 MiB limit")
    with path.open("rb") as source:
        data = source.read(MAX_SCHEMA_BYTES + 1)
    if len(data) > MAX_SCHEMA_BYTES:
        raise ValueError("Installed schema exceeds the 1 MiB limit")
    schema = json.loads(data)
    if not isinstance(schema, dict):
        raise ValueError("Installed contract schema must be an object")
    return schema, data

def schema_operation(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Read installed contracts and validate bounded inline documents, offline."""
    if operation not in {"read", "validate"} or not isinstance(arguments, dict):
        raise ValueError("Unsupported schema operation")
    allowed = {"name"} if operation == "read" else {"name", "document", "max_issues"}
    if set(arguments) - allowed:
        raise ValueError("Unexpected schema-operation arguments")
    catalog = installed_schema_catalog()
    name = arguments.get("name")
    if operation == "read" and name is None:
        descriptors = []
        for filename, path in sorted(catalog.items()):
            schema, data = _read_schema(path)
            declaration = schema.get("properties", {}).get("contract", {})
            contracts = [declaration["const"]] if "const" in declaration else declaration.get("enum", [])
            descriptors.append({"name": filename, "title": schema.get("title", filename),
                "id": schema.get("$id", filename), "dialect": schema.get("$schema", ""),
                "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "contracts": contracts})
        revision = hashlib.sha256(json.dumps(descriptors, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"schemas": sorted(catalog), "descriptors": descriptors, "catalog_revision": revision,
                "validation_is_not_solver_admission": True}
    if not isinstance(name, str) or name not in catalog:
        raise ValueError("Choose a schema filename from spike_contract_schema; arbitrary paths are not accepted")
    schema, data = _read_schema(catalog[name])
    if operation == "read":
        return {"name": name, "schema": schema, "sha256": hashlib.sha256(data).hexdigest(),
                "validation_is_not_solver_admission": True}
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
    document = arguments["document"]
    encoded = json.dumps(document, allow_nan=False, ensure_ascii=True)
    if len(encoded.encode()) > MAX_DOCUMENT_BYTES:
        raise ValueError("Contract document exceeds the 8 MiB limit")
    maximum = arguments.get("max_issues", 50)
    if type(maximum) is not int or not 1 <= maximum <= 500:
        raise ValueError("max_issues must be an integer from 1 to 500")
    # Dependencies are loaded lazily from this fixed catalog; unrelated schemas
    # do not need to be parsed for every small validation request.
    root_resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    resources = [(catalog[name].resolve().as_uri(), root_resource),
                 (str(schema.get("$id") or name), root_resource),
                 ("https://spike.local/schemas/" + name, root_resource)]
    def retrieve_local(uri: str) -> Resource:
        filename = uri.rsplit("/", 1)[-1]
        if filename not in catalog:
            raise ValueError("Schema reference is not in the installed SPIKE catalog")
        contents, _ = _read_schema(catalog[filename])
        return Resource.from_contents(contents, default_specification=DRAFT202012)
    registry = Registry(retrieve=retrieve_local).with_resources(resources)
    validator = jsonschema.validators.validator_for(schema)(schema, registry=registry)
    errors = list(itertools.islice(validator.iter_errors(document), maximum + 1))
    truncated = len(errors) > maximum
    shown = sorted(errors[:maximum], key=lambda item: str(list(item.path)))
    return {"name": name, "valid": not errors, "issues": [
        {"path": ".".join(map(str, error.path)), "message": error.message} for error in shown],
        "issue_count": len(errors), "issue_count_exact": not truncated, "issues_truncated": truncated,
        "validation_is_not_solver_admission": True}
