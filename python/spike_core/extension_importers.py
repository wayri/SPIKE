"""Executable extension importer contributions, using the normal import registry."""
from dataclasses import asdict
import json

from .contracts import DesignIR, ValidationIssue
from .importers import ImporterDescriptor


class ExtensionDesignImporter:
    def __init__(self, extension, contribution):
        self.extension = extension
        self.contribution = contribution
        self.descriptor = ImporterDescriptor(
            importer_id=contribution["id"], display_name=contribution["name"],
            source_formats=tuple(contribution["source_formats"]), extensions=tuple(contribution["extensions"]),
            accepts_directories=contribution.get("accepts_directories", False),
            extension_id=extension.manifest.id, status=extension.manifest.state,
        )

    def import_design(self, path):
        from .importers import ImportPolicy
        return self.import_with_policy(path, ImportPolicy(), {})

    def import_with_policy(self, path, policy, options):
        if "filesystem.workspace" not in self.extension.manifest.permissions:
            raise PermissionError("Importer extension requires filesystem.workspace permission.")
        result = self.extension.invoke(self.contribution["id"], {
            "source": {"path": path, "policy": asdict(policy), "options": options},
        }, timeout_seconds=policy.timeout_seconds)
        if result.get("status") not in {"completed", "completed_with_warnings"}:
            raise ValueError(f"Importer extension did not complete: {result.get('status')}")
        raw = result.get("data", {}).get("design")
        if not isinstance(raw, dict) or raw.get("contract") != "spike/v1":
            raise ValueError("Extension importer must return data.design using spike/v1.")
        # Reject NaN/Infinity even when a third party JSON writer allows them.
        json.dumps(raw, allow_nan=False)
        design = DesignIR(**raw)
        if not isinstance(design.metadata, dict):
            raise ValueError("Imported metadata must be an object.")
        for name in ("layers", "nets", "tracks", "vias", "pads", "zones", "components", "stackup"):
            if not isinstance(getattr(design, name), list) or any(not isinstance(r, dict) for r in getattr(design, name)):
                raise ValueError(f"Imported {name} must be an array of records.")
        design.issues = [ValidationIssue(**row) for row in design.issues]
        return design
