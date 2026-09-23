import unittest
import xml.etree.ElementTree as ET

from python.spike_core.ipc2581_contour import normalize_contours


FIXTURE = '''<IPC-2581>
  <DictionaryFillDesc units="INCH"><EntryFillDesc id="SOLID"><FillDesc fillProperty="FILL" /></EntryFillDesc></DictionaryFillDesc>
  <Ecad><CadData><Step><LayerFeature layerRef="PWR1"><Set net="GND"><Features>
    <Contour><Polygon><PolyBegin x="0" y="0" /><PolyStepSegment x="2" y="0" /><PolyStepSegment x="2" y="2" /><PolyStepSegment x="0" y="2" /><PolyStepSegment x="0" y="0" /><FillDescRef id="SOLID" /></Polygon>
    <Cutout><PolyBegin x="1.2" y="1" /><PolyStepCurve x="0.8" y="1" centerX="1" centerY="1" clockwise="true" /><PolyStepCurve x="1.2" y="1" centerX="1" centerY="1" clockwise="true" /></Cutout></Contour>
  </Features></Set></LayerFeature></Step></CadData></Ecad>
</IPC-2581>'''


def run(payload=FIXTURE, *, polarity="POSITIVE", resolve_net=True):
    root = ET.fromstring(payload)
    indices = {id(element): index for index, element in enumerate(root.iter())}
    issues = []
    zones, normalized, retained = normalize_contours(
        root, unit_factor=25.4, layer_lookup={"PWR1": "PWR1"}, layer_polarities={"PWR1": polarity},
        net_lookup={"GND": "GND"} if resolve_net else {}, element_indices=indices, seen_geometry_ids=set(),
        geometry_issue=lambda code, message, *, source_id="": issues.append((code, source_id, message)),
    )
    return zones, normalized, retained, issues


class Ipc2581ContourImportTests(unittest.TestCase):
    def test_losslessly_imports_solid_positive_contour_and_circular_cutout(self):
        zones, normalized, retained, issues = run()
        self.assertEqual((normalized, retained, issues), (1, [], []))
        zone = zones[0]
        self.assertEqual((zone["layer"], zone["net_id"], zone["ipc2581_fill_style"]), ("PWR1", "GND", "SOLID"))
        self.assertEqual(zone["id"], "contour:10")
        self.assertEqual([ring["role"] for ring in zone["boundary_rings"]], ["outer", "cutout"])
        self.assertEqual(zone["boundary_rings"][0]["start_mm"], [0.0, 0.0])
        self.assertEqual(zone["boundary_rings"][0]["segments"][0], {"kind": "line", "end_mm": [50.8, 0.0]})
        arcs = zone["boundary_rings"][1]["segments"]
        self.assertEqual([(arc["kind"], arc["center_mm"], arc["clockwise"]) for arc in arcs], [("arc", [25.4, 25.4], True)] * 2)

    def test_anonymous_identity_is_deterministic(self):
        first, _, _, _ = run()
        second, _, _, _ = run()
        self.assertEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(first[0]["source_index"], second[0]["source_index"])

    def test_rejects_bad_contour_atomically(self):
        payload = FIXTURE.replace('net="GND"', 'net="MISSING"')
        zones, normalized, retained, issues = run(payload)
        self.assertEqual((zones, normalized), ([], 0))
        self.assertEqual(retained, [])
        self.assertEqual(issues[0][0], "IMPORT_IPC2581_NET_REF_UNRESOLVED")

    def test_rejects_unclosed_ring_atomically(self):
        payload = FIXTURE.replace('x="0" y="0" /><FillDescRef', 'x="0" y="1" /><FillDescRef')
        zones, normalized, retained, issues = run(payload)
        self.assertEqual((zones, normalized), ([], 0))
        self.assertEqual(retained, [])
        self.assertEqual(issues[0][0], "IMPORT_IPC2581_CONTOUR_MALFORMED")

    def test_rejects_mixed_unit_fill_dictionary_atomically(self):
        payload = FIXTURE.replace('DictionaryFillDesc units="INCH"', 'DictionaryFillDesc units="MM"')
        zones, normalized, retained, issues = run(payload)
        self.assertEqual((zones, normalized), ([], 0))
        self.assertEqual(retained, [])
        self.assertEqual(issues[0][0], "IMPORT_IPC2581_CONTOUR_MALFORMED")

    def test_retains_exact_negative_contour_without_zone_or_fill_semantics(self):
        zones, normalized, retained, issues = run(polarity="NEGATIVE")
        self.assertEqual((zones, normalized, issues), ([], 0, []))
        self.assertEqual(len(retained), 1)
        record = retained[0]
        self.assertEqual(
            {key: record[key] for key in (
                "status", "reason", "source_id", "source_index", "layer_ref",
                "resolved_layer_id", "layer_polarity", "raw_net_ref", "resolved_net_id",
                "raw_fill_ref", "observed_fill_property",
            )},
            {
                "status": "retained_unresolved",
                "reason": "negative_layer_contour_semantics_pending",
                "source_id": "contour:10", "source_index": 10,
                "layer_ref": "PWR1", "resolved_layer_id": "PWR1",
                "layer_polarity": "NEGATIVE", "raw_net_ref": "GND",
                "resolved_net_id": "GND", "raw_fill_ref": "SOLID",
                "observed_fill_property": "FILL",
            },
        )
        self.assertEqual([item["role"] for item in record["boundary_rings"]], ["outer", "cutout"])
        self.assertEqual(record["boundary_rings"][1]["segments"][0]["center_mm"], [25.4, 25.4])

    def test_negative_contour_retains_raw_unresolved_net_without_connectivity(self):
        zones, normalized, retained, issues = run(polarity="NEGATIVE", resolve_net=False)
        self.assertEqual((zones, normalized, issues), ([], 0, []))
        self.assertEqual(
            (retained[0]["raw_net_ref"], retained[0]["resolved_net_id"]),
            ("GND", ""),
        )


if __name__ == "__main__":
    unittest.main()
