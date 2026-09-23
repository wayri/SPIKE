import tempfile
import unittest
from pathlib import Path

from python.spike_core.importers import FunctionImporter, ImporterDescriptor, ImporterRegistry
from python.spike_core.ipc2581_importer import import_ipc2581_design


PAD_VIA_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<IPC-2581 revision="C" name="Inline circle pad/via fixture" units="MM">
  <Ecad>
    <CadHeader>
      <Layer id="L1" name="TOP" layerType="conductor" />
      <Layer id="L2" name="DIEL1" layerType="dielectric" />
      <Layer id="L3" name="BOTTOM" layerType="conductor" />
      <StackupLayer layerRef="TOP" type="conductor" thickness="0.035" material="copper" />
      <StackupLayer layerRef="DIEL1" type="dielectric" thickness="1.5" material="FR4" />
      <StackupLayer layerRef="BOTTOM" type="conductor" thickness="0.035" material="copper" />
      <LogicalNet id="N1" name="VCC" />
      <Component id="C1" refDes="U1" part="IC" packageRef="QFN" layerRef="TOP" />
      <PadStackDef name="SMD_CIRCLE">
        <PadstackPadDef layerRef="TOP" padUse="REGULAR">
          <Location x="0" y="0" /><Circle diameter="1.2" />
        </PadstackPadDef>
      </PadStackDef>
      <PadStackDef name="PTH_CIRCLE">
        <PadstackHoleDef platingStatus="PLATED" diameter="0.6">
          <Location x="0" y="0" />
        </PadstackHoleDef>
        <PadstackPadDef layerRef="TOP" padUse="REGULAR">
          <Location x="0" y="0" /><Circle diameter="1.4" />
        </PadstackPadDef>
        <PadstackPadDef layerRef="BOTTOM" padUse="REGULAR">
          <Location x="0" y="0" /><Circle diameter="1.4" />
        </PadstackPadDef>
      </PadStackDef>
      <PadStackDef name="VIA_CIRCLE">
        <PadstackHoleDef platingStatus="VIA" diameter="0.4">
          <Location x="0" y="0" />
        </PadstackHoleDef>
        <PadstackPadDef layerRef="TOP" padUse="REGULAR">
          <Location x="0" y="0" /><Circle diameter="0.8" />
        </PadstackPadDef>
        <PadstackPadDef layerRef="BOTTOM" padUse="REGULAR">
          <Location x="0" y="0" /><Circle diameter="0.8" />
        </PadstackPadDef>
      </PadStackDef>
    </CadHeader>
    <CadData><Step>
      <LayerFeature layerRef="L1"><Set netRef="N1"><Features>
        <Pad id="SMD-1" padstackDefRef="SMD_CIRCLE">
          <Location x="10" y="20" /><Circle diameter="1.2" />
          <PinRef componentRef="C1" pin="1" />
        </Pad>
        <Pad id="PTH-1" padstackDefRef="PTH_CIRCLE">
          <Location x="20" y="30" /><Circle diameter="1.4" />
          <PinRef componentRef="C1" pin="2" />
        </Pad>
        <Pad id="VIA-1" padstackDefRef="VIA_CIRCLE">
          <Location x="30" y="40" /><Circle diameter="0.8" />
        </Pad>
      </Features></Set></LayerFeature>
      <LayerFeature layerRef="L3"><Set netRef="N1"><Features>
        <Pad id="PTH-1" padstackDefRef="PTH_CIRCLE">
          <Location x="20" y="30" /><Circle diameter="1.4" />
        </Pad>
        <Pad id="VIA-1" padstackDefRef="VIA_CIRCLE">
          <Location x="30" y="40" /><Circle diameter="0.8" />
        </Pad>
      </Features></Set></LayerFeature>
    </Step></CadData>
  </Ecad>
</IPC-2581>
"""


class Ipc2581PadViaImportTests(unittest.TestCase):
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

    def import_outcome(self, payload: str):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "pad-via.ipc2581"
            source.write_text(payload, encoding="utf-8")
            return self.registry().import_outcome(str(source))

    @staticmethod
    def layer_names(outcome, layer_ids):
        by_id = {layer.id: layer.name for layer in outcome.design.layers}
        return [by_id[layer_id] for layer_id in layer_ids]

    @staticmethod
    def codes(outcome):
        return {item["code"] for item in outcome.report.geometry_errors}

    def test_imports_inline_circle_smd_pth_and_through_via(self):
        outcome = self.import_outcome(PAD_VIA_FIXTURE)

        self.assertEqual(outcome.report.coverage["pads"], 2)
        self.assertEqual(outcome.report.coverage["vias"], 1)
        self.assertTrue(outcome.report.solver_readiness["pi_dc"]["ready"])

        pads = {pad.source_id: pad for pad in outcome.design.pads}
        smd = pads["SMD-1"]
        self.assertEqual(smd.name, "1")
        self.assertEqual(smd.center_mm, (10.0, 20.0))
        self.assertEqual(smd.size_mm, (1.2, 1.2))
        self.assertEqual(smd.shape, "circle")
        self.assertEqual(smd.drill_shape, "none")
        self.assertFalse(smd.plated)
        self.assertEqual(self.layer_names(outcome, smd.layer_ids), ["TOP"])
        self.assertEqual(smd.component_id, outcome.design.components[0].id)

        pth = pads["PTH-1"]
        self.assertEqual(pth.name, "2")
        self.assertEqual(pth.center_mm, (20.0, 30.0))
        self.assertEqual(pth.size_mm, (1.4, 1.4))
        self.assertEqual(pth.drill_size_mm, (0.6, 0.6))
        self.assertEqual(pth.drill_shape, "circle")
        self.assertTrue(pth.plated)
        self.assertEqual(self.layer_names(outcome, pth.layer_ids), ["TOP", "BOTTOM"])
        self.assertEqual(pth.component_id, outcome.design.components[0].id)

        via = outcome.design.vias[0]
        self.assertEqual(via.source_id, "VIA-1")
        self.assertEqual(via.center_mm, (30.0, 40.0))
        self.assertEqual(via.diameter_mm, 0.8)
        self.assertEqual(via.drill_mm, 0.4)
        self.assertEqual(via.via_type, "through")
        self.assertEqual(self.layer_names(outcome, [via.start_layer_id, via.end_layer_id]), ["TOP", "BOTTOM"])

    def test_namespaced_fixture_has_the_same_typed_geometry(self):
        namespaced = PAD_VIA_FIXTURE.replace(
            '<IPC-2581 revision=', '<IPC-2581 xmlns="urn:ipc2581:test" revision=', 1
        )
        plain = self.import_outcome(PAD_VIA_FIXTURE)
        qualified = self.import_outcome(namespaced)

        self.assertEqual(qualified.report.coverage, plain.report.coverage)
        self.assertEqual(
            [(pad.source_id, pad.center_mm, pad.size_mm, pad.drill_size_mm, pad.plated)
             for pad in qualified.design.pads],
            [(pad.source_id, pad.center_mm, pad.size_mm, pad.drill_size_mm, pad.plated)
             for pad in plain.design.pads],
        )
        self.assertEqual(
            [(via.source_id, via.center_mm, via.diameter_mm, via.drill_mm)
             for via in qualified.design.vias],
            [(via.source_id, via.center_mm, via.diameter_mm, via.drill_mm)
             for via in plain.design.vias],
        )

    def test_unresolved_standard_primitive_reference_is_rejected_without_emitting_geometry(self):
        payload = PAD_VIA_FIXTURE.replace(
            '<Location x="0" y="0" /><Circle diameter="1.2" />',
            '<Location x="0" y="0" /><StandardPrimitiveRef primitiveRef="ROUND" />',
            1,
        )
        outcome = self.import_outcome(payload)

        self.assertEqual(outcome.report.coverage["pads"], 1)
        self.assertEqual(outcome.report.coverage["vias"], 1)
        self.assertTrue(any(code.startswith("IMPORT_IPC2581_PADSTACK_UNSUPPORTED") for code in self.codes(outcome)))
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])

    def test_resolves_standard_circle_dictionary_reference(self):
        payload = PAD_VIA_FIXTURE.replace(
            "  <Ecad>",
            '''  <DictionaryStandard units="MM">
    <EntryStandard id="SMD_LAND"><Circle diameter="1.2" /></EntryStandard>
  </DictionaryStandard>
  <Ecad>''',
            1,
        ).replace(
            '<Location x="0" y="0" /><Circle diameter="1.2" />',
            '<Location x="0" y="0" /><StandardPrimitiveRef id="SMD_LAND" />',
            1,
        ).replace(
            '<Location x="10" y="20" /><Circle diameter="1.2" />',
            '<Location x="10" y="20" /><StandardPrimitiveRef id="SMD_LAND" />',
            1,
        )
        outcome = self.import_outcome(payload)

        self.assertEqual(outcome.report.coverage["pads"], 2)
        self.assertEqual(outcome.report.coverage["vias"], 1)
        self.assertEqual(next(pad for pad in outcome.design.pads if pad.source_id == "SMD-1").size_mm, (1.2, 1.2))
        self.assertTrue(outcome.report.solver_readiness["pi_dc"]["ready"])

    def test_standard_dictionary_units_are_converted_independently(self):
        payload = PAD_VIA_FIXTURE.replace(
            "  <Ecad>",
            '''  <DictionaryStandard units="INCH">
    <EntryStandard id="SMD_LAND"><Circle diameter="0.05" /></EntryStandard>
  </DictionaryStandard>
  <Ecad>''',
            1,
        ).replace(
            '<Location x="0" y="0" /><Circle diameter="1.2" />',
            '<Location x="0" y="0" /><StandardPrimitiveRef id="SMD_LAND" />',
            1,
        ).replace(
            '<Location x="10" y="20" /><Circle diameter="1.2" />',
            '<Location x="10" y="20" /><StandardPrimitiveRef id="SMD_LAND" />',
            1,
        )
        outcome = self.import_outcome(payload)

        smd = next(pad for pad in outcome.design.pads if pad.source_id == "SMD-1")
        self.assertEqual(smd.center_mm, (10.0, 20.0))
        self.assertEqual(smd.size_mm, (1.27, 1.27))

    def test_heterogeneous_standard_circle_rect_profiles_are_lossless_and_use_first_layer_nominal(self):
        payload = PAD_VIA_FIXTURE.replace(
            "  <Ecad>",
            '''  <DictionaryStandard units="INCH">
    <EntryStandard id="PTH_TOP"><Circle diameter="0.05" /></EntryStandard>
    <EntryStandard id="PTH_BOTTOM"><RectCenter width="0.08" height="0.06" /></EntryStandard>
  </DictionaryStandard>
  <Ecad>''',
            1,
        )
        definition_land = '<Location x="0" y="0" /><Circle diameter="1.4" />'
        payload = payload.replace(
            definition_land, '<Location x="0" y="0" /><StandardPrimitiveRef id="PTH_TOP" />', 1,
        ).replace(
            definition_land, '<Location x="0" y="0" /><StandardPrimitiveRef id="PTH_BOTTOM" />', 1,
        )
        occurrence_land = '<Location x="20" y="30" /><Circle diameter="1.4" />'
        payload = payload.replace(
            occurrence_land, '<Location x="20" y="30" /><StandardPrimitiveRef id="PTH_TOP" />', 1,
        ).replace(
            occurrence_land, '<Location x="20" y="30" /><StandardPrimitiveRef id="PTH_BOTTOM" />', 1,
        )

        outcome = self.import_outcome(payload)
        pth = next(pad for pad in outcome.design.pads if pad.source_id == "PTH-1")

        # Existing v1 nominal values remain anchored to the first physical
        # copper layer while the exact heterogeneous lands remain available.
        self.assertEqual(pth.shape, "circle")
        self.assertEqual(pth.size_mm, (1.27, 1.27))
        profiles = pth.land_profiles
        self.assertEqual(
            [(self.layer_names(outcome, [profile.layer_id])[0], profile.use, profile.shape,
              profile.source_primitive_id) for profile in profiles],
            [("TOP", "regular", "circle", "PTH_TOP"),
             ("BOTTOM", "regular", "rect", "PTH_BOTTOM")],
        )
        self.assertEqual(profiles[0].size_mm, (1.27, 1.27))
        self.assertAlmostEqual(profiles[1].size_mm[0], 2.032)
        self.assertAlmostEqual(profiles[1].size_mm[1], 1.524)
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])
        self.assertIn("IMPORT_IPC2581_LAND_PROFILE_MESHING_PENDING", {item.code for item in outcome.design.issues})

    def test_heterogeneous_standard_circle_via_profiles_use_largest_diameter_nominal(self):
        payload = PAD_VIA_FIXTURE.replace(
            "  <Ecad>",
            '''  <DictionaryStandard units="MM">
    <EntryStandard id="VIA_TOP"><Circle diameter="0.8" /></EntryStandard>
    <EntryStandard id="VIA_BOTTOM"><Circle diameter="1.0" /></EntryStandard>
  </DictionaryStandard>
  <Ecad>''',
            1,
        )
        definition_land = '<Location x="0" y="0" /><Circle diameter="0.8" />'
        payload = payload.replace(
            definition_land, '<Location x="0" y="0" /><StandardPrimitiveRef id="VIA_TOP" />', 1,
        ).replace(
            definition_land, '<Location x="0" y="0" /><StandardPrimitiveRef id="VIA_BOTTOM" />', 1,
        )
        occurrence_land = '<Location x="30" y="40" /><Circle diameter="0.8" />'
        payload = payload.replace(
            occurrence_land, '<Location x="30" y="40" /><StandardPrimitiveRef id="VIA_TOP" />', 1,
        ).replace(
            occurrence_land, '<Location x="30" y="40" /><StandardPrimitiveRef id="VIA_BOTTOM" />', 1,
        )

        outcome = self.import_outcome(payload)
        via = outcome.design.vias[0]

        self.assertEqual(via.diameter_mm, 1.0)
        self.assertEqual(
            [(self.layer_names(outcome, [profile.layer_id])[0], profile.shape, profile.size_mm,
              profile.source_primitive_id) for profile in via.land_profiles],
            [("TOP", "circle", (0.8, 0.8), "VIA_TOP"),
             ("BOTTOM", "circle", (1.0, 1.0), "VIA_BOTTOM")],
        )
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])

    def test_heterogeneous_land_with_inline_profile_is_rejected_atomically(self):
        payload = PAD_VIA_FIXTURE.replace(
            "  <Ecad>",
            '''  <DictionaryStandard units="MM">
    <EntryStandard id="PTH_TOP"><Circle diameter="1.4" /></EntryStandard>
  </DictionaryStandard>
  <Ecad>''',
            1,
        )
        definition_land = '<Location x="0" y="0" /><Circle diameter="1.4" />'
        payload = payload.replace(
            definition_land, '<Location x="0" y="0" /><StandardPrimitiveRef id="PTH_TOP" />', 1,
        ).replace(
            definition_land, '<Location x="0" y="0" /><Circle diameter="1.6" />', 1,
        )
        occurrence_land = '<Location x="20" y="30" /><Circle diameter="1.4" />'
        payload = payload.replace(
            occurrence_land, '<Location x="20" y="30" /><StandardPrimitiveRef id="PTH_TOP" />', 1,
        ).replace(
            occurrence_land, '<Location x="20" y="30" /><Circle diameter="1.6" />', 1,
        )

        outcome = self.import_outcome(payload)

        self.assertNotIn("PTH-1", {pad.source_id for pad in outcome.design.pads})
        self.assertEqual(outcome.report.coverage["pads"], 1)
        self.assertIn("IMPORT_IPC2581_PADSTACK_UNSUPPORTED_LANDS", self.codes(outcome))

    def test_official_style_plated_hole_with_via_set_usage_is_a_through_via(self):
        payload = """<IPC-2581 revision="C" units="MM">
          <Layer id="TOP" name="TOP" layerFunction="CONDUCTOR" />
          <Layer id="BOT" name="BOTTOM" layerFunction="CONDUCTOR" />
          <StackupLayer layerOrGroupRef="TOP" thickness="0.035" />
          <StackupLayer layerOrGroupRef="BOTTOM" thickness="0.035" />
          <LogicalNet name="VCC" />
          <DictionaryStandard units="MM">
            <EntryStandard id="LAND"><Circle diameter="0.8" /></EntryStandard>
          </DictionaryStandard>
          <PadStackDef name="VIA_STACK">
            <PadstackHoleDef diameter="0.4" platingStatus="PLATED" x="0" y="0" />
            <PadstackPadDef layerRef="TOP" padUse="REGULAR">
              <Location x="0" y="0" /><StandardPrimitiveRef id="LAND" />
            </PadstackPadDef>
            <PadstackPadDef layerRef="BOTTOM" padUse="REGULAR">
              <Location x="0" y="0" /><StandardPrimitiveRef id="LAND" />
            </PadstackPadDef>
          </PadStackDef>
          <Step name="BOARD">
            <LayerFeature layerRef="TOP"><Set net="VCC" padUsage="VIA">
              <Pad padstackDefRef="VIA_STACK"><Location x="5" y="6" /><StandardPrimitiveRef id="LAND" /></Pad>
            </Set></LayerFeature>
            <LayerFeature layerRef="BOTTOM"><Set net="VCC" padUsage="VIA">
              <Pad padstackDefRef="VIA_STACK"><Location x="5" y="6" /><StandardPrimitiveRef id="LAND" /></Pad>
            </Set></LayerFeature>
          </Step>
        </IPC-2581>"""
        outcome = self.import_outcome(payload)

        self.assertEqual(outcome.report.coverage["pads"], 0)
        self.assertEqual(outcome.report.coverage["vias"], 1)
        self.assertEqual(outcome.design.vias[0].center_mm, (5.0, 6.0))
        self.assertEqual(outcome.design.vias[0].drill_mm, 0.4)
        self.assertTrue(outcome.report.solver_readiness["pi_dc"]["ready"])

    def test_drill_at_or_above_land_diameter_is_rejected(self):
        payload = PAD_VIA_FIXTURE.replace('diameter="0.6">\n          <Location', 'diameter="1.4">\n          <Location', 1)
        outcome = self.import_outcome(payload)

        self.assertEqual(outcome.report.coverage["pads"], 1)
        self.assertEqual(outcome.report.coverage["vias"], 1)
        self.assertTrue(any(code.startswith("IMPORT_IPC2581_PAD_MALFORMED") for code in self.codes(outcome)))
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])

    def test_missing_required_bottom_occurrence_fails_closed(self):
        payload = PAD_VIA_FIXTURE.replace(
            '''        <Pad id="PTH-1" padstackDefRef="PTH_CIRCLE">
          <Location x="20" y="30" /><Circle diameter="1.4" />
        </Pad>
''',
            "",
            1,
        )
        outcome = self.import_outcome(payload)

        self.assertEqual(outcome.report.coverage["pads"], 1)
        self.assertEqual(outcome.report.coverage["vias"], 1)
        self.assertTrue(any(code.startswith("IMPORT_IPC2581_OCCURRENCES_INCOMPLETE") for code in self.codes(outcome)))
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])
        retained = outcome.design.retained_padstack_occurrence_groups
        self.assertEqual(len(retained), 1)
        group = retained[0]
        self.assertEqual((group.id, group.padstack_ref, group.occurrence_count), ("PTH-1", "PTH_CIRCLE", 1))
        self.assertEqual([outcome.design.to_v1().metadata["ipc2581_incomplete_pad_occurrence_groups"][0][key]
                          for key in ("expected_regular_layer_ids", "observed_layer_ids")], [["TOP", "BOTTOM"], ["TOP"]])
        occurrence = group.occurrences[0]
        self.assertIsInstance(occurrence.source_index, int)
        self.assertEqual((occurrence.source_id, occurrence.pad_usage, occurrence.at_mm), ("PTH-1", "", (20.0, 30.0)))
        self.assertEqual((occurrence.shape.kind, occurrence.shape.size_mm, occurrence.shape.source_primitive_id),
                         ("circle", (1.4, 1.4), ""))
        self.assertEqual((occurrence.pin.pin, group.status), ("2", "retained_unresolved"))

    def test_retains_complete_unnetted_padstack_group_without_typed_geometry(self):
        payload = """<IPC-2581 revision="C" units="MM">
          <Layer id="TOP" name="TOP" layerType="conductor" polarity="POSITIVE" />
          <Layer id="BOTTOM" name="BOTTOM" layerType="conductor" polarity="POSITIVE" />
          <DictionaryStandard units="MM"><EntryStandard id="LAND"><Circle diameter="1.0" /></EntryStandard></DictionaryStandard>
          <PadStackDef name="MOUNTING_HOLE">
            <PadstackHoleDef platingStatus="PLATED" diameter="0.6"><Location x="0" y="0" /></PadstackHoleDef>
            <PadstackPadDef layerRef="TOP" padUse="REGULAR"><Location x="0" y="0" /><StandardPrimitiveRef id="LAND" /></PadstackPadDef>
            <PadstackPadDef layerRef="BOTTOM" padUse="REGULAR"><Location x="0" y="0" /><StandardPrimitiveRef id="LAND" /></PadstackPadDef>
          </PadStackDef>
          <Step>
            <LayerFeature layerRef="TOP"><Set plate="true" testPoint="false"><Features>
              <Pad padstackDefRef="MOUNTING_HOLE"><Xform rotation="90.000" /><Location x="5" y="6" /><StandardPrimitiveRef id="LAND" /></Pad>
            </Features></Set></LayerFeature>
            <LayerFeature layerRef="BOTTOM"><Set plate="true" testPoint="false"><Features>
              <Pad padstackDefRef="MOUNTING_HOLE"><Xform rotation="90.000" /><Location x="5" y="6" /><StandardPrimitiveRef id="LAND" /></Pad>
            </Features></Set></LayerFeature>
          </Step>
        </IPC-2581>"""
        outcome = self.import_outcome(payload)

        self.assertEqual((outcome.report.coverage["pads"], outcome.report.coverage["vias"]), (0, 0))
        retained = outcome.design.to_v1().metadata["ipc2581_retained_unnetted_padstack_occurrence_groups"]
        self.assertEqual(retained["contract"], "spike/retained-unnetted-padstack-groups/v1")
        self.assertEqual(len(retained["groups"]), 1)
        group = retained["groups"][0]
        self.assertEqual((group["status"], group["reason"], group["occurrence_count"]),
                         ("retained_unresolved", "native_net_identity_absent", 2))
        self.assertEqual(group["expected_regular_layer_ids"], ["TOP", "BOTTOM"])
        self.assertEqual([item["shape"]["source_primitive_id"] for item in group["occurrences"]], ["LAND", "LAND"])
        self.assertEqual(group["occurrences"][0]["xform"], {
            "rotation_deg": 90.0, "mirror": False, "raw_attributes": {"rotation": "90.000"},
        })
        self.assertEqual(group["occurrences"][0]["raw_set_attributes"], {"plate": "true", "testpoint": "false"})
        coverage = outcome.design.metadata["geometry_coverage"]
        self.assertEqual(coverage["normalized_retained_unnetted_pad_occurrences"], 2)
        self.assertEqual(coverage["unsupported_or_unresolved"], 0)
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])

        unknown = self.import_outcome(payload.replace('<Set plate="true" testPoint="false">', '<Set netRef="UNKNOWN">'))
        self.assertNotIn("ipc2581_retained_unnetted_padstack_occurrence_groups", unknown.design.to_v1().metadata)
        self.assertIn("IMPORT_IPC2581_NET_REF_UNRESOLVED", self.codes(unknown))

    def test_retains_exact_negative_plane_thermal_user_primitive_without_typed_geometry(self):
        payload = """<IPC-2581 revision="C" units="MM">
          <Layer id="TOP" name="TOP" layerType="conductor" polarity="POSITIVE" />
          <Layer id="PLANE" name="GND1" layerType="plane" polarity="NEGATIVE" />
          <LogicalNet id="GND" name="GND" />
          <DictionaryUser units="MM"><EntryUser id="FULL_CONTACT"><UserSpecial>
            <Contour><Polygon><PolyBegin x="1" y="0" />
              <PolyStepCurve x="-1" y="0" centerX="0" centerY="0" clockwise="false" />
              <PolyStepCurve x="1" y="0" centerX="0" centerY="0" clockwise="false" />
              <FillDescRef id="SOLID" />
            </Polygon></Contour>
          </UserSpecial></EntryUser></DictionaryUser>
          <PadStackDef name="BGA_VIA">
            <PadstackHoleDef platingStatus="VIA" diameter="0.4"><Location x="0" y="0" /></PadstackHoleDef>
            <PadstackPadDef layerRef="TOP" padUse="REGULAR"><Location x="0" y="0" /><Circle diameter="0.8" /></PadstackPadDef>
            <PadstackPadDef layerRef="PLANE" padUse="REGULAR"><Location x="0" y="0" /><Circle diameter="0.8" /></PadstackPadDef>
            <PadstackPadDef layerRef="PLANE" padUse="THERMAL"><Location x="0" y="0" /><UserPrimitiveRef id="FULL_CONTACT" /></PadstackPadDef>
          </PadStackDef>
          <Step><LayerFeature layerRef="PLANE"><Set netRef="GND" padUsage="VIA"><Features>
            <Pad id="VIA-PLANE" padstackDefRef="BGA_VIA"><Location x="10" y="20" />
              <Xform rotation="90" mirror="true" /><UserPrimitiveRef id="FULL_CONTACT" />
            </Pad>
          </Features></Set></LayerFeature></Step>
        </IPC-2581>"""
        outcome = self.import_outcome(payload)

        self.assertEqual(outcome.design.metadata["parser_revision"], "ipc2581-conductor-primitives-v13")
        self.assertIsNotNone(outcome.design.retained_nonregular_padstack_geometry)
        retained = outcome.design.to_v1().metadata["ipc2581_retained_nonregular_padstack_geometry"]
        self.assertEqual(retained["contract"], "spike/retained-padstack-geometry/v1")
        self.assertEqual(len(retained["user_primitives"]), 1)
        definition = retained["user_primitives"][0]
        self.assertEqual((definition["id"], definition["kind"], definition["source_units"]),
                         ("FULL_CONTACT", "user_special", "MM"))
        ring = definition["contours"][0]["boundary_rings"][0]
        self.assertEqual((ring["role"], tuple(ring["start_mm"]), [item["kind"] for item in ring["segments"]]),
                         ("outer", (1.0, 0.0), ["arc", "arc"]))
        occurrence = retained["occurrences"][0]
        self.assertEqual(
            {key: occurrence[key] for key in (
                "source_id", "kind", "status", "reason", "padstack_ref", "layer_id", "layer_polarity",
                "raw_net_ref", "resolved_net_id", "occurrence_pad_usage", "matched_profile_use", "xform", "primitive_ref",
            )},
            {
                "source_id": "VIA-PLANE", "kind": "retained_padstack_nonregular_occurrence",
                "status": "retained_unresolved", "reason": "negative_plane_user_primitive_semantics_pending",
                "padstack_ref": "BGA_VIA", "layer_id": "GND1", "layer_polarity": "negative",
                "raw_net_ref": "GND", "resolved_net_id": "GND", "occurrence_pad_usage": "via",
                "matched_profile_use": "thermal",
                "xform": {"rotation_deg": 90.0, "mirror": True}, "primitive_ref": "FULL_CONTACT",
            },
        )
        self.assertEqual(tuple(occurrence["at_mm"]), (10.0, 20.0))
        self.assertEqual((outcome.report.coverage["pads"], outcome.report.coverage["vias"]), (0, 0))
        self.assertEqual(
            outcome.design.metadata["geometry_coverage"]["normalized_retained_nonregular_padstack_occurrences"], 1,
        )
        self.assertFalse(outcome.report.solver_readiness["pi_dc"]["ready"])

    def test_retains_standard_contour_land_as_source_only_without_typed_or_connectivity_semantics(self):
        payload = """<IPC-2581 revision="C" units="MM">
          <Layer id="TOP" name="TOP" layerType="conductor" polarity="POSITIVE" />
          <Layer id="BOTTOM" name="BOTTOM" layerType="conductor" polarity="POSITIVE" />
          <LogicalNet id="VCC" name="VCC" />
          <Component id="C1" refDes="U1" part="R" packageRef="R0402" layerRef="TOP" />
          <DictionaryFillDesc units="INCH"><EntryFillDesc id="SOLID_FILL">
            <FillDesc fillProperty="FILL" />
          </EntryFillDesc></DictionaryFillDesc>
          <DictionaryStandard units="INCH"><EntryStandard id="SHAPE_S20"><Contour><Polygon>
            <PolyBegin x="-0.010000" y="-0.010000" />
            <PolyStepSegment x="0.010000" y="-0.010000" />
            <PolyStepSegment x="0.010000" y="0.010000" />
            <PolyStepSegment x="-0.010000" y="0.010000" />
            <PolyStepSegment x="-0.010000" y="-0.010000" />
            <FillDescRef id="SOLID_FILL" />
          </Polygon></Contour></EntryStandard></DictionaryStandard>
          <PadStackDef name="NS_S20_SAP_21SP"><PadstackPadDef layerRef="TOP" padUse="REGULAR">
            <Xform xOffset="0.0" yOffset="0.0" rotation="0" mirror="false" faceUp="true" scale="1.0" />
            <Location x="0.0" y="0.0" /><StandardPrimitiveRef id="SHAPE_S20" />
          </PadstackPadDef></PadStackDef>
          <Step>
            <LayerFeature layerRef="TOP"><Set net="VCC" testPoint="false"><Pad padstackDefRef="NS_S20_SAP_21SP">
              <Xform rotation="90.000" /><Location x="10" y="20" /><StandardPrimitiveRef id="SHAPE_S20" />
              <PinRef pin="1" componentRef="C1" />
            </Pad></Set></LayerFeature>
            <LayerFeature layerRef="BOTTOM"><Set net="VCC" testPoint="false"><Pad padstackDefRef="NS_S20_SAP_21SP">
              <Xform xOffset="1.5" yOffset="-2.5" rotation="360.000" mirror="true" faceUp="false" scale="1.0" />
              <Location x="11" y="20" /><StandardPrimitiveRef id="SHAPE_S20" />
              <PinRef pin="2" componentRef="C1" />
            </Pad></Set></LayerFeature>
          </Step>
        </IPC-2581>"""
        outcome = self.import_outcome(payload)

        self.assertEqual((outcome.report.coverage["pads"], outcome.report.coverage["vias"]), (0, 0))
        typed_retained = outcome.design.retained_standard_contour_land_geometry
        self.assertEqual(
            (typed_retained.semantic_state, typed_retained.projection),
            ("unapplied_normative_semantics_missing", "forbidden"),
        )
        self.assertEqual((typed_retained.occurrences[0].xform.rotation_deg, typed_retained.occurrences[0].xform.mirror), (90.0, False))
        self.assertEqual((typed_retained.occurrences[1].xform.rotation_deg, typed_retained.occurrences[1].xform.mirror), (360.0, True))
        retained = outcome.design.to_v1().metadata["ipc2581_retained_standard_contour_land_geometry"]
        self.assertEqual(retained["contract"], "spike/retained-standard-contour-land-geometry/v2")
        self.assertEqual(
            (retained["semantic_state"], retained["projection"]),
            ("unapplied_normative_semantics_missing", "forbidden"),
        )
        self.assertEqual((len(retained["definitions"]), len(retained["padstacks"]), len(retained["occurrences"])),
                         (1, 1, 2))
        definition = retained["definitions"][0]
        self.assertEqual((definition["id"], definition["source_units"], definition["fill_descriptor"]["declared_fill_property"]),
                         ("SHAPE_S20", "INCH", "FILL"))
        self.assertEqual(definition["contour"]["points_mm"], [
            [-0.254, -0.254], [0.254, -0.254], [0.254, 0.254], [-0.254, 0.254], [-0.254, -0.254],
        ])
        self.assertEqual(retained["padstacks"][0]["profile_xform"], {
            "rotation_deg": 0.0, "mirror": False, "x_offset_mm": 0.0, "y_offset_mm": 0.0,
            "face_up": True, "scale": 1.0,
            "raw_attributes": {"faceup": "true", "mirror": "false", "rotation": "0", "scale": "1.0", "xoffset": "0.0", "yoffset": "0.0"},
        })
        top, bottom = retained["occurrences"]
        self.assertEqual((top["declared_regular_layer_id"], top["observed_layer_id"]), ("TOP", "TOP"))
        self.assertEqual((bottom["declared_regular_layer_id"], bottom["observed_layer_id"]), ("TOP", "BOTTOM"))
        self.assertTrue(top["declared_layer_matches_observed"])
        self.assertFalse(bottom["declared_layer_matches_observed"])
        self.assertEqual(bottom["xform"], {
            "rotation_deg": 360.0, "mirror": True,
            "x_offset_mm": 1.5, "y_offset_mm": -2.5, "face_up": False, "scale": 1.0,
            "raw_attributes": {"faceup": "false", "mirror": "true", "rotation": "360.000", "scale": "1.0", "xoffset": "1.5", "yoffset": "-2.5"},
        })
        self.assertEqual(bottom["pin_provenance"]["pin"], "2")
        self.assertEqual(bottom["pin_provenance"]["component_layer_id"], "TOP")
        coverage = outcome.design.metadata["geometry_coverage"]
        self.assertEqual(coverage["normalized_retained_standard_contour_land_occurrences"], 2)
        self.assertEqual(coverage["normalized_retained_standard_contour_land_declared_layer_matches"], 1)
        self.assertEqual(coverage["normalized_retained_standard_contour_land_declared_layer_mismatches"], 1)
        self.assertEqual(coverage["retained_standard_contour_land_empirical_distribution"], {
            "label": "empirical_source_observation_not_conformance",
            "profile_xforms": [{"padstack_ref": "NS_S20_SAP_21SP", "rotation_deg": 0.0, "mirror": False}],
            "occurrences": [
                {"declared_regular_layer_id": "TOP", "observed_layer_id": "BOTTOM", "rotation_deg": 360.0, "mirror": True, "count": 1},
                {"declared_regular_layer_id": "TOP", "observed_layer_id": "TOP", "rotation_deg": 90.0, "mirror": False, "count": 1},
            ],
        })
        self.assertEqual(coverage["unsupported_or_unresolved"], 0)
        self.assertFalse(outcome.design.metadata["geometry_solver_ready"])
        self.assertTrue(all(not item["ready"] for item in outcome.report.solver_readiness.values()))

        unresolved = self.import_outcome(payload.replace('<Set net="VCC" testPoint="false">',
                                                         '<Set net="UNKNOWN" testPoint="false">', 1))
        retained_unresolved = unresolved.design.to_v1().metadata.get(
            "ipc2581_retained_standard_contour_land_geometry", {"occurrences": []},
        )
        self.assertEqual(len(retained_unresolved["occurrences"]), 1)
        self.assertIn("IMPORT_IPC2581_NET_REF_UNRESOLVED", self.codes(unresolved))


if __name__ == "__main__":
    unittest.main()
