from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"studio/python"))
from spikes_studio.document import Document, RC_DECK, Keymap
from spikes_studio.signal_math import SignalMath, Quantity, VOLT, AMP, SECOND, ExpressionError
from spikes_studio.result_file import save_result, load_result
from spikes_studio.ide import read_vcd
from spikes_studio.interchange import import_text


class SignalMathTests(unittest.TestCase):
    def setUp(self):
        self.t=np.array([0.,.1,.4,1.])
        self.math=SignalMath(self.t,{"v(out)":Quantity(self.t,VOLT),"v(ref)":Quantity(self.t*.5,VOLT),"i(R1)":Quantity(np.ones(4)*2,AMP)})

    def test_differential_power_and_time_integral_on_irregular_grid(self):
        q=self.math.evaluate("v(out,ref)*i(R1)")
        np.testing.assert_allclose(q.values,self.t)
        self.assertEqual(q.unit,VOLT.mul(AMP))
        q=self.math.evaluate("integral(v(out))")
        np.testing.assert_allclose(q.values,self.t**2/2)
        self.assertEqual(q.unit,VOLT.mul(SECOND))
        self.assertAlmostEqual(float(self.math.evaluate("mean(v(out))").values),.5)
        np.testing.assert_allclose(self.math.evaluate("derivative(v(out))").values,1)

    def test_functions_equation_and_crossings(self):
        self.math.signals['v(in)']=self.math.signals['v(out)']
        np.testing.assert_allclose(self.math.evaluate('v(in,ref)').values,self.t/2)
        np.testing.assert_allclose(self.math.evaluate('V(IN,REF)').values,self.t/2)
        np.testing.assert_allclose(self.math.evaluate('SIN(V(out)/V)').values,np.sin(self.t))
        np.testing.assert_allclose(self.math.evaluate("sin(v(out)/V)**2 + cos(v(out)/V)**2").values,1)
        self.assertAlmostEqual(self.math.solve("cos(x)-x",0,1),.7390851332,places=9)
        self.assertEqual(self.math.crossings("v(out)",.3),[.3])
        np.testing.assert_allclose(self.math.evaluate("where(v(out)>0.3*V,v(out),0*V)").values,[0,0,.4,1])

    def test_unit_domain_and_code_errors_are_rejected(self):
        for text in ("v(out)+i(R1)","exp(v(out))","1/0","log(-1)","__import__('os')","v(out).__class__","[x for x in t]","2**101"):
            with self.subTest(text=text),self.assertRaises((ExpressionError,ValueError)):self.math.evaluate(text)

    def test_archive_preserves_complex_samples_units_and_provenance(self):
        self.math.signals["complex"]=Quantity(self.t+1j*self.t,VOLT)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"record.spkdata";save_result(path,self.math,{"source_sha256":"a"*64},chunk_samples=2)
            restored,provenance=load_result(path)
            self.assertEqual(provenance["source_sha256"],"a"*64)
            np.testing.assert_array_equal(restored.time,self.t)
            np.testing.assert_array_equal(restored.signals["complex"].values,self.math.signals["complex"].values)
            with self.assertRaises(FileExistsError):save_result(path,self.math,{})


class EditingTests(unittest.TestCase):
    def test_property_updates_source_and_undo_redo_round_trip(self):
        doc=Document.from_netlist(RC_DECK);part=doc.data["components"][1]
        doc.update([part["id"]],{"value":"2k","nodes":["in","out"],"limits":{"power_w":.25},"model_source":"* evidence"})
        self.assertIn("R1 in out 2k",doc.data["source"])
        doc.undo();self.assertIn("R1 in out 1k",doc.data["source"])
        doc.redo();self.assertEqual(doc.data["components"][1]["limits"],{"power_w":.25})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"doc.spksch";doc.save(path);self.assertEqual(Document.load(path).data,doc.data)

    def test_bulk_edit_is_atomic_on_bad_value_and_unknown_probe(self):
        doc=Document.from_netlist(RC_DECK);before=doc.data["source"]
        with self.assertRaises(ValueError):doc.update([doc.data["components"][1]["id"]],{"value":"bogus"})
        self.assertEqual(doc.data["source"],before)
        with self.assertRaises(ValueError):doc.add_probe("V(missing)")
        doc.add_probe("V(in,out)");self.assertEqual(len(doc.data["probes"]),1)

    def test_keyboard_profiles_and_conflicts(self):
        for profile in ("SPIKES","KiCad-inspired","LTspice-inspired"):Keymap.preset(profile)
        with self.assertRaises(ValueError):Keymap({"file.open":"Ctrl+O","file.save":"ctrl+o"})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"keys.spkkeys";keys=Keymap();keys.save(path);self.assertEqual(Keymap.load(path).bindings,keys.bindings)

    def test_inventory_import_does_not_invent_electrical_translation(self):
        report=import_text('(kicad_sch (version 20250114) (symbol (property "Reference" "R1") (property "Value" "1k")))')
        self.assertIsNone(report.document);self.assertEqual(report.inventory[0]["Reference"],"R1")
        self.assertTrue(report.warnings)

    def test_vcd_hierarchy_aliases_unknown_and_vector_values(self):
        data=read_vcd('$timescale 10 ns $end\n$scope module top $end\n$var wire 1 ! clk $end\n$var wire 2 # bus $end\n$upscope $end\n$enddefinitions $end\n#0\nx!\nb01 #\n#2\n1!\nb11 #\n#3')
        self.assertAlmostEqual(data["end_time_s"],3e-8)
        self.assertEqual(data["signals"]["top.bus"]["transitions"][-1][1],"11")
        self.assertEqual(data["signals"]["top.clk"]["transitions"][0][1],"x")


if __name__=="__main__":unittest.main()
