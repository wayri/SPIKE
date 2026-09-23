import tempfile
import unittest
from pathlib import Path

from python.spike_core.importers import FunctionImporter, ImporterDescriptor, ImporterRegistry
from python.spike_core.ipc2581_importer import import_ipc2581_design
from tests.python.test_ipc2581_pad_via_import import PAD_VIA_FIXTURE


def drill_fixture(*, bad_tolerance: bool = False) -> str:
    tolerance = "-0.01" if bad_tolerance else "0.01"
    payload = PAD_VIA_FIXTURE.replace(
        '<Layer id="L3" name="BOTTOM" layerType="conductor" />',
        '<Layer id="L3" name="BOTTOM" layerType="conductor" />\n      <Layer id="D1" name="DRILL_1-2" layerType="drill" />',
    )
    return payload.replace(
        "    </Step></CadData>",
        f'''      <LayerFeature layerRef="D1">
        <Set netRef="N1" geometry="VIA_CIRCLE">
          <Hole name="H-VIA" x="30" y="40" diameter="0.4" platingStatus="VIA" plusTol="0" minusTol="0" />
        </Set>
        <Set netRef="N1" geometry="PTH_CIRCLE" componentRef="C1">
          <Hole name="H-PAD" x="20" y="30" diameter="0.6" platingStatus="PLATED" plusTol="{tolerance}" minusTol="0" />
        </Set>
        <Set geometry="TOOL">
          <Hole name="H-NPTH" x="50" y="60" diameter="1.0" platingStatus="UNPLATED" plusTol="0" minusTol="0" />
        </Set>
      </LayerFeature>
    </Step></CadData>''',
    )


class Ipc2581DrillImportTests(unittest.TestCase):
    @staticmethod
    def registry():
        return ImporterRegistry([FunctionImporter(
            descriptor=ImporterDescriptor(
                importer_id="ipc-2581", display_name="IPC-2581",
                source_formats=("ipc-2581", "ipc2581"), extensions=(".ipc2581",),
            ),
            implementation=import_ipc2581_design,
        )])

    def import_outcome(self, payload: str):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "drills.ipc2581"
            source.write_text(payload, encoding="utf-8")
            return self.registry().import_outcome(str(source))

    def test_preserves_physical_drills_and_links_exact_owners_without_new_copper(self):
        outcome = self.import_outcome(drill_fixture())

        self.assertEqual(outcome.report.coverage["drills"], 3)
        self.assertEqual((outcome.report.coverage["pads"], outcome.report.coverage["vias"]), (2, 1))
        self.assertTrue(outcome.report.solver_readiness["pi_dc"]["ready"])
        drills = {item.source_id: item for item in outcome.design.drills}
        via = drills["H-VIA"]
        pad = drills["H-PAD"]
        npth = drills["H-NPTH"]
        self.assertEqual((via.plating_status, via.owner_kind, via.owner_id, via.owner_match),
                         ("via", "via", outcome.design.vias[0].id, "exact_source"))
        self.assertEqual((pad.plating_status, pad.owner_kind, pad.owner_id, pad.owner_match),
                         ("plated", "pad", next(item.id for item in outcome.design.pads if item.source_id == "PTH-1"), "exact_source"))
        self.assertEqual((npth.plating_status, npth.plated, npth.owner_kind, npth.owner_id),
                         ("unplated", False, "none", ""))
        self.assertEqual(pad.plus_tolerance_mm, 0.01)
        self.assertEqual(len(via.span_layer_ids), 2)
        self.assertEqual(outcome.design.to_v1().metadata["manufacturing_drills"][0]["owner_id"], "VIA-1")

    def test_malformed_hole_is_rejected_without_partial_drill(self):
        outcome = self.import_outcome(drill_fixture(bad_tolerance=True))

        self.assertEqual(outcome.report.coverage["drills"], 2)
        self.assertNotIn("H-PAD", {item.source_id for item in outcome.design.drills})
        self.assertIn("IMPORT_IPC2581_DRILL_MALFORMED", {item["code"] for item in outcome.report.geometry_errors})
        coverage = outcome.design.metadata["geometry_coverage"]
        self.assertEqual(coverage["normalized_drills"], 2)
        self.assertEqual(coverage["unsupported_or_unresolved"], 1)


if __name__ == "__main__":
    unittest.main()
