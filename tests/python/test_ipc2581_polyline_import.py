import tempfile
import unittest
from pathlib import Path

from python.spike_core.importers import FunctionImporter, ImporterDescriptor, ImporterRegistry
from python.spike_core.ipc2581_importer import import_ipc2581_design


def polyline_fixture(*, units="MM", width="0.25", style_id="ROUND_TRACE", steps=None, entries=""):
    steps = steps or '<PolyStepSegment x="10" y="0" />'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<IPC-2581 revision="C">
  <DictionaryLineDesc units="{units}">
    <EntryLineDesc id="{style_id}"><LineDesc lineEnd="ROUND" lineWidth="{width}" /></EntryLineDesc>
    {entries}
  </DictionaryLineDesc>
  <Ecad>
    <CadHeader units="{units}">
      <Layer id="L1" name="TOP" layerType="conductor" />
      <Layer id="L2" name="DIEL1" layerType="dielectric" />
      <Layer id="L3" name="BOTTOM" layerType="conductor" />
      <StackupLayer layerRef="TOP" type="conductor" thickness="0.035" material="copper" />
      <StackupLayer layerRef="DIEL1" type="dielectric" thickness="1.0" material="FR4" />
      <StackupLayer layerRef="BOTTOM" type="conductor" thickness="0.035" material="copper" />
      <LogicalNet id="N1" name="VCC" />
    </CadHeader>
    <CadData><Step>
      <LayerFeature layerRef="L1"><Set net="N1"><Features>
        <Polyline><PolyBegin x="0" y="0" />{steps}<LineDescRef id="{style_id}" /></Polyline>
      </Features></Set></LayerFeature>
    </Step></CadData>
  </Ecad>
</IPC-2581>'''


class Ipc2581PolylineImportTests(unittest.TestCase):
    @staticmethod
    def registry():
        return ImporterRegistry([FunctionImporter(
            descriptor=ImporterDescriptor(
                importer_id="ipc-2581",
                display_name="IPC-2581",
                source_formats=("ipc-2581", "ipc2581"),
                extensions=(".ipc2581",),
            ),
            implementation=import_ipc2581_design,
        )])

    def import_outcome(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "polyline.ipc2581"
            source.write_text(payload, encoding="utf-8")
            return self.registry().import_outcome(str(source))

    def test_imports_one_step_round_polyline_as_a_deterministic_track(self):
        first = self.import_outcome(polyline_fixture())
        second = self.import_outcome(polyline_fixture())

        self.assertEqual(first.report.coverage["tracks"], 1)
        self.assertEqual(first.report.coverage["arcs"], 0)
        self.assertTrue(first.report.solver_readiness["pi_dc"]["ready"])
        track = first.design.tracks[0]
        self.assertEqual(track.net_id, first.design.nets[0].id)
        self.assertEqual(track.layer_id, next(layer.id for layer in first.design.layers if layer.name == "TOP"))
        self.assertEqual((track.start_mm, track.end_mm, track.width_mm), ((0.0, 0.0), (10.0, 0.0), 0.25))
        self.assertTrue(track.source_id)
        self.assertEqual(track.source_id, second.design.tracks[0].source_id)
        coverage = first.design.metadata["geometry_coverage"]
        self.assertEqual(
            {key: coverage[key] for key in ("declared", "normalized_tracks", "normalized_arcs", "normalized_source_records", "unsupported_or_unresolved")},
            {"declared": 1, "normalized_tracks": 1, "normalized_arcs": 0, "normalized_source_records": 1, "unsupported_or_unresolved": 0},
        )

    def test_namespace_equivalence_and_inch_conversion(self):
        plain = polyline_fixture(units="INCH", width="0.01", steps='<PolyStepSegment x="1" y="0" />')
        namespaced = plain.replace('<IPC-2581 revision=', '<IPC-2581 xmlns="urn:ipc2581:test" revision=', 1)
        base = self.import_outcome(plain)
        qualified = self.import_outcome(namespaced)

        self.assertEqual(qualified.report.coverage, base.report.coverage)
        self.assertEqual(qualified.report.solver_readiness, base.report.solver_readiness)
        self.assertEqual(
            (qualified.design.tracks[0].source_id, qualified.design.tracks[0].start_mm, qualified.design.tracks[0].end_mm, qualified.design.tracks[0].width_mm),
            (base.design.tracks[0].source_id, base.design.tracks[0].start_mm, base.design.tracks[0].end_mm, base.design.tracks[0].width_mm),
        )
        self.assertEqual(base.design.tracks[0].end_mm, (25.4, 0.0))
        self.assertEqual(base.design.tracks[0].width_mm, 0.254)

    def test_line_dictionary_units_must_match_ecad_units(self):
        payload = polyline_fixture(units="MM", width="0.01").replace(
            'DictionaryLineDesc units="MM"', 'DictionaryLineDesc units="INCH"', 1
        )
        outcome = self.import_outcome(payload)

        self.assertEqual(outcome.report.coverage["tracks"], 0)
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])
        self.assertTrue(outcome.report.geometry_errors)

    def test_multistep_round_polyline_is_one_typed_atomic_path(self):
        outcome = self.import_outcome(polyline_fixture(
            steps='<PolyStepSegment x="5" y="0" /><PolyStepSegment x="10" y="5" />'
        ))

        self.assertEqual(outcome.report.coverage["tracks"], 2)
        self.assertEqual(outcome.report.coverage["arcs"], 0)
        self.assertTrue(outcome.report.solver_readiness["pi_dc"]["ready"])
        path_id = outcome.design.tracks[0].path.path_id
        self.assertEqual([track.source_id for track in outcome.design.tracks], [
            f"{path_id}:segment:1", f"{path_id}:segment:2",
        ])
        self.assertEqual(
            [(track.path.path_id, track.path.step_index, track.path.step_count, track.path.end_cap, track.path.join_style)
             for track in outcome.design.tracks],
            [(path_id, 0, 2, "round", "round"), (path_id, 1, 2, "round", "round")],
        )
        coverage = outcome.design.metadata["geometry_coverage"]
        self.assertEqual(
            (coverage["declared"], coverage["normalized_tracks"], coverage["normalized_source_records"], coverage["unsupported_or_unresolved"]),
            (1, 2, 1, 0),
        )

    def test_curve_polyline_is_rejected_atomically(self):
        outcome = self.import_outcome(polyline_fixture(
            steps='<PolyStepSegment x="0.5" y="0" /><PolyStepCurve x="1" y="0" centerX="0.75" centerY="0" clockwise="true" />'
        ))
        self.assertEqual(outcome.report.coverage["tracks"], 0)
        self.assertEqual(outcome.report.coverage["arcs"], 0)
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])
        self.assertTrue(outcome.report.geometry_errors)
        coverage = outcome.design.metadata["geometry_coverage"]
        self.assertEqual((coverage["declared"], coverage["normalized_source_records"], coverage["unsupported_or_unresolved"]), (1, 0, 1))

    def test_bad_line_descriptor_fails_closed(self):
        duplicate = '<EntryLineDesc id="ROUND_TRACE"><LineDesc lineEnd="ROUND" lineWidth="0.25" /></EntryLineDesc>'
        cases = {
            "unknown": polyline_fixture().replace('LineDescRef id="ROUND_TRACE"', 'LineDescRef id="MISSING"'),
            "zero-width": polyline_fixture(width="0"),
            "duplicate": polyline_fixture(entries=duplicate),
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                outcome = self.import_outcome(payload)
                self.assertEqual((outcome.report.coverage["tracks"], outcome.report.coverage["arcs"]), (0, 0))
                self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])
                self.assertTrue(outcome.report.geometry_errors)
                coverage = outcome.design.metadata["geometry_coverage"]
                self.assertEqual((coverage["normalized_source_records"], coverage["unsupported_or_unresolved"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
