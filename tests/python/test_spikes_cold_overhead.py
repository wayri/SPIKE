# SPDX-License-Identifier: Apache-2.0
"""Native channel extraction retains scalar ABI values and lifetime errors."""
import contextlib,io,json,os,tempfile,unittest,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from python.spikes.native_abi import load_native_library,NativeABIError
from python.spikes.native_io_pad import IO_PAD_SYMBOLS,require_io_pad_api
from python.spikes.cli import main
ROOT=Path(__file__).resolve().parents[2]
DLL=Path(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll'))

class CapabilityAdmissionTests(unittest.TestCase):
    def test_partial_pad_api_fails_before_binding(self):
        library=SimpleNamespace(_library=SimpleNamespace(spikes_circuit_add_io_pad=object()))
        with self.assertRaisesRegex(NativeABIError,'spikes_transient_session_set_io_pad'):
            require_io_pad_api(library)

    @unittest.skipUnless(DLL.is_file(),'owned library required')
    def test_basic_native_cli_does_not_import_help_or_behavioral_stack(self):
        script="""import sys
class Blocker:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('shutil','bz2','lzma','python.spikes.behavioral'):
   raise AssertionError('Unneeded cold-start import: '+fullname)
sys.meta_path.insert(0,Blocker())
from python.spikes.cli import main
raise SystemExit(main(['native-run',sys.argv[1],'--library',sys.argv[2]]))
"""
        with tempfile.TemporaryDirectory() as temp:
            deck=Path(temp)/'divider.cir'
            deck.write_text('Divider\nV1 in 0 1\nR1 in out 1k\nR2 out 0 1k\n.op\n.end\n')
            run=subprocess.run([sys.executable,'-c',script,str(deck),str(DLL)],cwd=ROOT,capture_output=True,text=True,timeout=15)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads(run.stdout)['data']['node_voltage_v']['out'],.5)

    def test_package_rejects_old_dll_before_creating_output(self):
        old=ROOT/'build-spikes-native-analysis-20261013/Release/spikes_c_api.dll'
        if not old.is_file():self.skipTest('old DLL fixture unavailable')
        from scripts.build_spikes_studio_package import main as build
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'candidate'
            with patch('sys.argv',['build','--candidate','--output',str(target),'--library',str(old)]):
                with self.assertRaisesRegex(NativeABIError,'GPIO'):
                    build()
            self.assertFalse(target.exists())

@unittest.skipUnless(DLL.is_file(),'owned library required')
class ChannelExtractionTests(unittest.TestCase):
    def setUp(self):
        self.library=load_native_library(DLL)
        self.circuit=self.library.circuit();self.addCleanup(self.circuit.close)
        self.circuit.add_voltage_source('V1','in','0',1)
        self.circuit.add_resistor('R1','in','out',1000)
        self.circuit.add_capacitor('C1','out','0',1e-6)

    def solve(self):
        return self.circuit.solve_transient(time_step_s=1e-4,stop_time_s=1e-3,initialize_from_operating_point=False)

    def test_every_channel_matches_scalar_abi_exactly(self):
        with self.solve() as result:
            self.assertEqual(result.time_values(),[result.time(i) for i in range(result.point_count)])
            for method,scalar,names in ((result.node_voltage_values,result.node_voltage,['in','out']),
                (result.element_current_values,result.element_current,['V1','R1','C1']),
                (result.element_power_values,result.element_power,['V1','R1','C1'])):
                for name in names:self.assertEqual(method(name),[scalar(i,name) for i in range(result.point_count)])

    def test_closed_result_and_unknown_channel_fail(self):
        result=self.solve();result.close()
        with self.assertRaisesRegex(NativeABIError,'closed'):result.time_values()
        with self.solve() as result:
            with self.assertRaises(NativeABIError):result.node_voltage_values('missing')
            with self.assertRaises(ValueError):result.node_voltage_values('')

    def test_mid_series_native_error_is_propagated(self):
        with self.solve() as result:
            original=self.library._library.spikes_transient_result_point_time
            def query(handle,index,pointer):return 1 if index==2 else original(handle,index,pointer)
            with patch.object(self.library._library,'spikes_transient_result_point_time',side_effect=query):
                with self.assertRaisesRegex(NativeABIError,'point 2'):result.time_values()

    def test_pretty_and_compact_cli_keep_complete_json_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'rc.cir'
            path.write_text('RC\nV1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n.tran 100u 1m uic\n.end\n')
            outputs=[]
            for extra in ([],['--pretty']):
                stream=io.StringIO()
                with contextlib.redirect_stdout(stream):self.assertEqual(main(['native-run',str(path),'--library',str(DLL),*extra]),0)
                outputs.append(stream.getvalue())
            self.assertEqual(json.loads(outputs[0]),json.loads(outputs[1]))
            self.assertLess(len(outputs[0]),len(outputs[1]))
            self.assertEqual(len(outputs[0].splitlines()),1)
            self.assertIn('\n  "',outputs[1])
            output=Path(temp)/'result.json'
            self.assertEqual(main(['native-run',str(path),'--library',str(DLL),'-o',str(output)]),0)
            self.assertEqual(output.read_text(),outputs[1])
