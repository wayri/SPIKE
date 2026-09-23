import hashlib
import json
import math
import unittest
from dataclasses import FrozenInstanceError, replace

from python.spikes.model_builder import (
    LibraryExportError,
    ModelBuilder,
    ModelBuilderError,
    QualificationError,
    QualificationPolicy,
    ShockleyDiodeFitter,
    export_archetype,
    llm_draft_source,
    qualify_model,
)
from python.spikes.model_builder_contracts import (
    LIBRARY_EXPORT_CONTRACT,
    MODEL_PACKAGE_CONTRACT,
    BlackBoxDescriptor,
    CurveDataset,
    DatasetColumn,
    DomainBound,
    ParameterDefinition,
    QualificationRecord,
    SourceArtifact,
    ValidityEnvelope,
)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SpikesModelBuilderTests(unittest.TestCase):
    def make_builder(self, *, review_llm=False):
        source = SourceArtifact(
            source_id="vendor_datasheet",
            kind="datasheet",
            sha256=digest("datasheet bytes"),
            locator="file:///evidence/vendor-diode.pdf",
            title="Vendor diode datasheet",
            review_state="reviewed",
            reviewed_by="device-engineer",
            license="vendor redistribution restricted",
        )
        extracted = llm_draft_source(
            "llm_iv_curve",
            digest("page 4 curve extraction"),
            "artifact://vendor-diode/page/4/figure/2",
            "Draft forward I-V extraction",
            ("vendor_datasheet",),
        )
        builder = ModelBuilder(
            "spikes.generic:diode.fitted_test@1",
            "Fitted test diode",
            "semiconductor",
            "Shockley diode fitted from reviewed curve evidence.",
            ("anode", "cathode"),
        )
        builder.add_source(source).add_source(extracted)
        if review_llm:
            builder.review_source("llm_iv_curve", "device-engineer", "Compared every point to page 4.")
        builder.add_parameter(ParameterDefinition(
            name="saturation_current_a", unit="A", value=1e-12,
            minimum=1e-18, maximum=1e-6, description="Reverse saturation current.",
        ))
        builder.add_parameter(ParameterDefinition(
            name="ideality_factor", unit="1", value=1.5,
            minimum=0.5, maximum=4.0, description="Emission coefficient.",
        ))
        thermal_voltage = 1.380649e-23 * 298.15 / 1.602176634e-19
        rows = tuple(
            (voltage, 2.5e-12 * math.expm1(voltage / (1.72 * thermal_voltage)))
            for voltage in (0.18, 0.23, 0.28, 0.33, 0.38, 0.43, 0.48, 0.53)
        )
        builder.add_dataset(CurveDataset(
            dataset_id="forward_iv_25c",
            kind="datasheet_extracted",
            columns=(DatasetColumn("voltage_v", "V"), DatasetColumn("current_a", "A")),
            rows=rows,
            source_ids=("llm_iv_curve",),
            role="both",
            conditions={"temperature_c": 25.0},
        ))
        builder.set_validity(ValidityEnvelope(bounds=(
            DomainBound("voltage_v", "V", -10.0, 0.65),
            DomainBound("temperature_c", "degC", -20.0, 125.0),
        ), notes="voltage and junction-temperature envelope"))
        builder.set_black_box(BlackBoxDescriptor(
            black_box_id="shockley_diode_v1",
            implementation="spikes.compact.diode.shockley/v1",
            pins=("anode", "cathode"),
            observables=("current_a", "power_w"),
            state_variables=("junction_temperature_c",),
            required_capabilities=("nonlinear_dc", "transient"),
        ))
        return builder

    def test_llm_extraction_is_always_created_as_untrusted_draft(self):
        draft = llm_draft_source(
            "draft", digest("draft"), "artifact://draft", "Draft", ("datasheet",)
        )
        self.assertEqual(draft.kind, "llm_extraction")
        self.assertEqual(draft.review_state, "unreviewed")
        self.assertFalse(draft.trusted_for_qualification)
        with self.assertRaises(ValueError):
            llm_draft_source("bad", digest("bad"), "artifact://bad", "Bad", ())

    def test_fit_is_deterministic_and_recovers_diode_parameters(self):
        first = self.make_builder(review_llm=True)
        second = self.make_builder(review_llm=True)
        result_a = first.fit("forward_iv_25c", ShockleyDiodeFitter())
        result_b = second.fit("forward_iv_25c", ShockleyDiodeFitter())
        self.assertEqual(result_a.to_dict(), result_b.to_dict())
        self.assertAlmostEqual(result_a.parameter_values["ideality_factor"], 1.72, places=8)
        self.assertAlmostEqual(result_a.parameter_values["saturation_current_a"], 2.5e-12, places=19)
        self.assertLess(result_a.metrics.values["log_rmse"], 1e-9)
        self.assertEqual(result_a.metrics.sample_count, 8)

    def test_unreviewed_llm_evidence_blocks_qualification_and_export(self):
        builder = self.make_builder()
        builder.fit("forward_iv_25c", ShockleyDiodeFitter())
        package = builder.build_draft()
        with self.assertRaisesRegex(QualificationError, "llm_iv_curve"):
            qualify_model(package, "qualification-engineer")
        with self.assertRaises(LibraryExportError):
            export_archetype(package)
        forged = replace(package, qualification=QualificationRecord(
            state="qualified", reviewer="attacker", policy_id="fake", checks=("fake",)
        ))
        with self.assertRaisesRegex(LibraryExportError, "safety floor"):
            export_archetype(forged)

    def test_qualified_package_and_export_are_versioned_json_contracts(self):
        builder = self.make_builder(review_llm=True)
        builder.fit("forward_iv_25c", ShockleyDiodeFitter())
        draft = builder.build_draft()
        qualified = qualify_model(draft, "qualification-engineer", notes="Fixture Q-17 passed.")
        exported = export_archetype(qualified)
        self.assertEqual(qualified.contract, MODEL_PACKAGE_CONTRACT)
        self.assertEqual(qualified.qualification.state, "qualified")
        self.assertTrue(qualified.verify_digest())
        self.assertEqual(exported.contract, LIBRARY_EXPORT_CONTRACT)
        self.assertTrue(exported.archetype.available)
        self.assertEqual(exported.archetype.archetype_id, qualified.model_id)
        self.assertEqual(
            exported.archetype.provenance["content_sha256"], qualified.content_sha256
        )
        json.dumps(exported.to_dict(), allow_nan=False, sort_keys=True)

    def test_content_and_nested_mappings_are_immutable(self):
        builder = self.make_builder(review_llm=True)
        builder.fit("forward_iv_25c", ShockleyDiodeFitter())
        package = builder.build_draft()
        with self.assertRaises(FrozenInstanceError):
            package.title = "changed"
        with self.assertRaises(TypeError):
            package.datasets[0].conditions["temperature_c"] = 150.0
        with self.assertRaises(TypeError):
            package.fit_results[0].parameter_values["ideality_factor"] = 3.0

    def test_digest_tampering_blocks_qualification_and_export(self):
        builder = self.make_builder(review_llm=True)
        builder.fit("forward_iv_25c", ShockleyDiodeFitter())
        draft = builder.build_draft()
        tampered = replace(draft, content_sha256="f" * 64)
        with self.assertRaisesRegex(QualificationError, "digest"):
            qualify_model(tampered, "qualification-engineer")
        qualified = qualify_model(draft, "qualification-engineer")
        with self.assertRaisesRegex(LibraryExportError, "digest"):
            export_archetype(replace(qualified, content_sha256="e" * 64))

    def test_metric_policy_fails_closed(self):
        builder = self.make_builder(review_llm=True)
        builder.fit("forward_iv_25c", ShockleyDiodeFitter())
        draft = builder.build_draft()
        impossible = QualificationPolicy(metric_maximums={"log_rmse": 0.0, "max_relative_error": 0.0})
        with self.assertRaisesRegex(QualificationError, "exceeds"):
            qualify_model(draft, "qualification-engineer", impossible)

    def test_parameter_dataset_and_black_box_validation_reject_bad_inputs(self):
        with self.assertRaises(ValueError):
            ParameterDefinition("gain", "1", math.nan)
        with self.assertRaises(ValueError):
            ParameterDefinition("gain", "1", 3.0, minimum=4.0)
        with self.assertRaises(ValueError):
            CurveDataset(
                "bad", "measured",
                (DatasetColumn("x", "V"), DatasetColumn("y", "A")),
                ((1.0,),), ("source",),
            )
        builder = self.make_builder(review_llm=True)
        with self.assertRaises(ModelBuilderError):
            builder.set_black_box(BlackBoxDescriptor(
                "wrong_pins", "test/v1", ("p", "n"), ("current_a",)
            ))


if __name__ == "__main__":
    unittest.main()
