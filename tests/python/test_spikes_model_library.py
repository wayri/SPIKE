import json
from dataclasses import FrozenInstanceError
import unittest

from python.spikes.model_library import (
    KiCadModelMapping,
    QualifiedModelLibrary,
    QualifiedModelRecord,
    RedistributionApproval,
)


MODEL_ID = "spikes.generic:diode.test@1"
DIGEST = "a" * 64


def approval(*, approved=True, digest=DIGEST):
    return RedistributionApproval(
        model_id=MODEL_ID, content_sha256=digest,
        license_expression="LicenseRef-SPIKES-Test-Redistributable",
        evidence_sha256="b" * 64, reviewer="release-engineer",
        approved=approved,
    )


def record():
    return QualifiedModelRecord(
        model_id=MODEL_ID, title="Qualified test diode", family="semiconductor.diode",
        pins=("anode", "cathode"), content_sha256=DIGEST,
        implementation="spikes.compact.diode.shockley/v1",
        qualification_policy="spikes.model.standard-v1",
        qualified_by="device-engineer", redistribution=approval(),
    )


class QualifiedModelLibraryTests(unittest.TestCase):
    def test_exact_kicad_mapping_round_trips_and_resolves(self):
        mapping = KiCadModelMapping(
            symbol_id="Device:D", model_id=MODEL_ID, model_content_sha256=DIGEST,
            pin_map={"1": "cathode", "2": "anode"},
            parameter_overrides={"temperature_k": 300.15},
        )
        library = QualifiedModelLibrary((record(),), (mapping,))
        restored = QualifiedModelLibrary.from_dict(json.loads(json.dumps(library.to_dict())))
        selected, binding = restored.resolve_kicad("Device:D")
        self.assertEqual(selected.content_sha256, DIGEST)
        self.assertEqual(binding.pin_map["1"], "cathode")
        with self.assertRaises(KeyError):
            restored.resolve_kicad("Device:Q_NPN_BCE")

    def test_unapproved_or_digest_mismatched_models_fail_closed(self):
        with self.assertRaises(ValueError):
            QualifiedModelRecord(
                model_id=MODEL_ID, title="D", family="diode",
                pins=("anode", "cathode"), content_sha256=DIGEST,
                implementation="test/v1", qualification_policy="policy",
                qualified_by="reviewer", redistribution=approval(approved=False),
            )
        mapping = KiCadModelMapping(
            "Device:D", MODEL_ID, "c" * 64, {"1": "cathode", "2": "anode"}
        )
        with self.assertRaises(ValueError):
            QualifiedModelLibrary((record(),), (mapping,))

    def test_pin_mapping_must_be_complete_one_to_one_and_immutable(self):
        with self.assertRaises(ValueError):
            KiCadModelMapping(
                "Device:D", MODEL_ID, DIGEST, {"1": "anode", "2": "anode"}
            )
        incomplete = KiCadModelMapping(
            "Device:D", MODEL_ID, DIGEST, {"1": "anode"}
        )
        with self.assertRaises(ValueError):
            QualifiedModelLibrary((record(),), (incomplete,))
        mapped = KiCadModelMapping(
            "Device:D", MODEL_ID, DIGEST, {"1": "cathode", "2": "anode"}
        )
        with self.assertRaises(TypeError):
            mapped.pin_map["1"] = "anode"
        with self.assertRaises(FrozenInstanceError):
            mapped.symbol_id = "Device:D_Small"

    def test_duplicate_symbol_and_model_ids_are_rejected(self):
        mapped = KiCadModelMapping(
            "Device:D", MODEL_ID, DIGEST, {"1": "cathode", "2": "anode"}
        )
        with self.assertRaises(ValueError):
            QualifiedModelLibrary((record(), record()), ())
        with self.assertRaises(ValueError):
            QualifiedModelLibrary((record(),), (mapped, mapped))


if __name__ == "__main__":
    unittest.main()
