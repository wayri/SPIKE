import tempfile
import unittest
from pathlib import Path
from unittest import mock

from python.spike_core.importers import FunctionImporter, ImporterDescriptor, ImporterRegistry
from python.spike_core.ipc2581_importer import import_ipc2581_design


FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<IPC-2581 revision="C" name="Neutral fixture">
  <Layer id="L1" name="TOP" layerType="conductor" />
  <Layer id="L2" name="DIEL1" layerType="dielectric" />
  <Layer id="L3" name="BOTTOM" layerType="conductor" />
  <StackupLayer layerRef="TOP" type="conductor" thickness="0.035" material="copper" />
  <StackupLayer layerRef="DIEL1" type="dielectric" thickness="1.5" material="FR4" />
  <StackupLayer layerRef="BOTTOM" type="conductor" thickness="0.035" material="copper" />
  <LogicalNet id="N1" name="VCC" />
  <Component id="C1" refDes="U1" part="REGULATOR" packageRef="QFN" layerRef="TOP" />
  <Feature><Set><Pad /></Set></Feature>
</IPC-2581>
"""

GEOMETRY_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<IPC-2581 xmlns="urn:ipc:2581" revision="C" name="Conductor fixture" units="INCH">
  <Ecad>
    <CadHeader>
      <Layer id="L1" name="TOP" layerType="conductor" />
      <Layer id="L2" name="DIEL1" layerType="dielectric" />
      <Layer id="L3" name="BOTTOM" layerType="conductor" />
      <StackupLayer layerRef="TOP" type="conductor" thickness="0.00137" material="copper" />
      <StackupLayer layerRef="DIEL1" type="dielectric" thickness="0.059" material="FR4" />
      <StackupLayer layerRef="BOTTOM" type="conductor" thickness="0.00137" material="copper" />
      <LogicalNet id="N1" name="VCC" />
    </CadHeader>
    <CadData><Step>
      <LayerFeature layerRef="L1"><Set netRef="N1"><Features>
        <Line id="T1" width="0.01">
          <PolyBegin x="0" y="0" /><PolyStepSegment x="1" y="0" />
        </Line>
        <Arc id="A1" width="0.01">
          <PolyBegin x="1" y="0" />
          <PolyStepCurve x="0" y="1" centerX="0" centerY="0" clockwise="false" />
        </Arc>
      </Features></Set></LayerFeature>
    </Step></CadData>
  </Ecad>
</IPC-2581>
"""

COVERAGE_SCOPE_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<IPC-2581 revision="C" units="MM">
  <Ecad><CadHeader>
    <Layer id="L1" name="TOP" layerType="conductor" />
    <Layer id="M1" name="MASK" layerType="soldermask" />
    <LogicalNet id="N1" name="GND" />
  </CadHeader><CadData><Step>
    <LayerFeature layerRef="L1"><Set net="N1"><Features>
      <Pad /><Contour><Polygon><PolyBegin x="0" y="0" /></Polygon></Contour>
    </Features></Set></LayerFeature>
    <LayerFeature layerRef="M1"><Set net="N1"><Features>
      <Pad /><Polyline id="MASK_ART"><PolyBegin x="0" y="0" /><PolyStepSegment x="1" y="0" /></Polyline>
    </Features></Set></LayerFeature>
  </Step></CadData></Ecad>
  <DictionaryStandard><EntryStandard id="PROFILE"><Contour><Polygon><PolyBegin x="0" y="0" /></Polygon></Contour></EntryStandard></DictionaryStandard>
</IPC-2581>
"""


class Ipc2581ImporterTests(unittest.TestCase):
    def registry(self):
        return ImporterRegistry([FunctionImporter(
            descriptor=ImporterDescriptor(
                importer_id="ipc-2581",
                display_name="IPC-2581",
                source_formats=("ipc-2581", "ipc2581"),
                extensions=(".ipc2581",),
            ),
            implementation=import_ipc2581_design,
        )])

    def test_imports_topology_and_reports_unimplemented_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.ipc2581"
            source.write_text(FIXTURE, encoding="utf-8")
            outcome = self.registry().import_outcome(str(source))
        self.assertEqual(outcome.design.source.source_format, "ipc-2581")
        self.assertEqual([layer.name for layer in outcome.design.layers], ["TOP", "DIEL1", "BOTTOM"])
        self.assertEqual([net.name for net in outcome.design.nets], ["VCC"])
        self.assertEqual(outcome.design.components[0].reference, "U1")
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])
        self.assertTrue(any(item["code"] == "IMPORT_IPC2581_GEOMETRY_PENDING" for item in outcome.report.diagnostics))

    def test_rejects_entity_declarations(self):
        payload = '<!DOCTYPE x [<!ENTITY y "bad">]><IPC-2581>&y;</IPC-2581>'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "unsafe.ipc2581"
            source.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DOCTYPE or ENTITY"):
                self.registry().import_design(str(source))

    def test_normalizes_explicit_line_and_circular_arc_with_unit_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "geometry.ipc2581"
            source.write_text(GEOMETRY_FIXTURE, encoding="utf-8")
            outcome = self.registry().import_outcome(str(source))
        self.assertEqual(outcome.report.coverage["tracks"], 1)
        self.assertEqual(outcome.report.coverage["arcs"], 1)
        self.assertEqual(outcome.design.tracks[0].source_id, "T1")
        self.assertEqual(outcome.design.arcs[0].source_id, "A1")
        self.assertAlmostEqual(outcome.design.tracks[0].end_mm[0], 25.4)
        self.assertAlmostEqual(outcome.design.tracks[0].width_mm, 0.254)
        self.assertAlmostEqual(outcome.design.layers[0].thickness_mm, 0.00137 * 25.4)
        self.assertAlmostEqual(outcome.design.arcs[0].mid_mm[0], 25.4 / 2 ** 0.5)
        self.assertAlmostEqual(outcome.design.arcs[0].mid_mm[1], 25.4 / 2 ** 0.5)
        self.assertTrue(outcome.report.solver_readiness["pi_dc"]["ready"])
        self.assertIn("T1", outcome.report.object_map)
        self.assertIn("A1", outcome.report.object_map)
        self.assertFalse(any(item["code"] == "IMPORT_IPC2581_GEOMETRY_PENDING" for item in outcome.report.diagnostics))

    def test_unknown_layer_reference_fails_closed_without_emitting_geometry(self):
        payload = GEOMETRY_FIXTURE.replace('layerRef="L1"><Set', 'layerRef="L404"><Set')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "unknown-layer.ipc2581"
            source.write_text(payload, encoding="utf-8")
            outcome = self.registry().import_outcome(str(source))
        self.assertEqual(outcome.report.coverage["tracks"], 0)
        self.assertEqual(outcome.report.coverage["arcs"], 0)
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])
        self.assertTrue(any(item["code"] == "IMPORT_IPC2581_LAYER_REF_UNRESOLVED" for item in outcome.report.geometry_errors))

    def test_unknown_net_width_and_invalid_arc_fail_closed(self):
        cases = {
            "unknown-net": (
                GEOMETRY_FIXTURE.replace('netRef="N1"', 'netRef="N404"'),
                "IMPORT_IPC2581_NET_REF_UNRESOLVED",
            ),
            "missing-width": (
                GEOMETRY_FIXTURE.replace(' id="T1" width="0.01"', ' id="T1"'),
                "IMPORT_IPC2581_WIDTH_UNRESOLVED",
            ),
            "invalid-arc": (
                GEOMETRY_FIXTURE.replace('x="0" y="1" centerX="0"', 'x="0" y="2" centerX="0"'),
                "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, (payload, expected_code) in cases.items():
                with self.subTest(name=name):
                    source = Path(directory) / f"{name}.ipc2581"
                    source.write_text(payload, encoding="utf-8")
                    outcome = self.registry().import_outcome(str(source))
                    self.assertTrue(any(item["code"] == expected_code for item in outcome.report.geometry_errors))
                    self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])

    def test_rejects_late_doctype_declaration(self):
        payload = (" " * (1024 * 1024 + 8)) + '<!DOCTYPE x [<!ENTITY y "bad">]><IPC-2581 />'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "late-unsafe.ipc2581"
            source.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DOCTYPE or ENTITY"):
                self.registry().import_design(str(source))

    def test_direct_parser_enforces_source_and_element_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bounded.ipc2581"
            source.write_text('<IPC-2581 units="MM"><Layer /></IPC-2581>', encoding="utf-8")
            with mock.patch("python.spike_core.ipc2581_importer.MAX_IPC2581_SOURCE_BYTES", 16):
                with self.assertRaisesRegex(ValueError, "parser limit"):
                    import_ipc2581_design(str(source))
            with mock.patch("python.spike_core.ipc2581_importer.MAX_IPC2581_XML_ELEMENTS", 1):
                with self.assertRaisesRegex(ValueError, "element resource limit"):
                    import_ipc2581_design(str(source))

    def test_geometry_diagnostics_are_bounded(self):
        payload = GEOMETRY_FIXTURE.replace('layerRef="L1"><Set', 'layerRef="L404"><Set')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "diagnostic-cap.ipc2581"
            source.write_text(payload, encoding="utf-8")
            with mock.patch("python.spike_core.ipc2581_importer.MAX_IPC2581_GEOMETRY_DIAGNOSTICS", 1):
                design = import_ipc2581_design(str(source))

        self.assertEqual(design.metadata["omitted_geometry_diagnostics"], 1)
        self.assertTrue(any(issue.code == "IMPORT_IPC2581_DIAGNOSTICS_TRUNCATED" for issue in design.issues))

    def test_geometry_coverage_excludes_non_copper_pads_polylines_and_out_of_scope_polygons(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "coverage-scope.ipc2581"
            source.write_text(COVERAGE_SCOPE_FIXTURE, encoding="utf-8")
            outcome = self.registry().import_outcome(str(source))

        coverage = outcome.design.metadata["geometry_coverage"]
        self.assertEqual(
            {key: coverage[key] for key in (
                "source_geometry_total", "excluded_non_copper_pad_occurrences", "excluded_non_copper_polyline_records",
                "excluded_out_of_scope_polyline_constructs", "excluded_out_of_scope_polygon_constructs", "scoped_contours", "declared",
            )},
            {
                "source_geometry_total": 5,
                "excluded_non_copper_pad_occurrences": 1,
                "excluded_non_copper_polyline_records": 1,
                "excluded_out_of_scope_polyline_constructs": 0,
                "excluded_out_of_scope_polygon_constructs": 1,
                "scoped_contours": 1,
                "declared": 2,
            },
        )
        self.assertEqual(coverage["unsupported_or_unresolved"], 2)
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])


if __name__ == "__main__":
    unittest.main()
