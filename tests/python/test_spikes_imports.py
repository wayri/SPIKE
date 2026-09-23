"""Keep the native CLI startup independent of optional analysis/UI imports."""
import subprocess
import sys
import unittest


class LazyPublicApiTests(unittest.TestCase):
    def test_public_exports_are_still_resolvable(self):
        import python.spikes as spikes
        self.assertEqual(spikes.__version__,spikes.ENGINE_VERSION)
        for name in spikes.__all__:
            with self.subTest(name=name):self.assertTrue(hasattr(spikes,name))

    def test_native_startup_does_not_import_numpy_or_gui(self):
        code=("import sys; import python.spikes.cli; "
              "from python.spikes import parse_netlist, run_native_project; "
              "assert 'numpy' not in sys.modules; assert 'wx' not in sys.modules")
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
