"""Run Studio regression tests and retain failures/skips as structured evidence."""
import argparse
import faulthandler
import io
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]
cache=ROOT/'.tmp/studio-deps'
if any((cache/'numpy'/'_core').glob(f'*.cp{sys.version_info.major}{sys.version_info.minor}-*.pyd')):
    sys.path.insert(0,str(cache))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--ngspice',type=Path)
    parser.add_argument('--wx',action='store_true',help='Enable opt-in native wx widget tests')
    parser.add_argument('--progress',action='store_true',help='Stream test identities for native-crash diagnostics')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    faulthandler.enable()
    library=args.library.resolve(strict=True)
    os.environ['SPIKES_TEST_LIBRARY']=str(library);os.environ['SPIKES_TEST_NATIVE_LIBRARY']=str(library)
    if args.ngspice:os.environ['SPIKES_TEST_NGSPICE']=str(args.ngspice.resolve(strict=True))
    if args.wx:os.environ['SPIKES_TEST_WX']='1'
    # Some older test modules prepend a historical cp311 cache. Bind the chosen
    # runtime's packages before discovery so those modules cannot substitute
    # incompatible extension modules into an already valid wx environment.
    if args.wx:
        import numpy
        import matplotlib
        # Native widgets share one application for the entire test process,
        # including discovery. Recreating wx.App between fixture lifetimes can
        # invalidate native state retained by deferred window callbacks.
        import wx
        application=wx.GetApp() or wx.App(False)
        application.SetExitOnFrameDelete(False)
    suite=unittest.defaultTestLoader.discover(str(ROOT/'standalone/spikes_project/tests/python'))
    class ProgressResult(unittest.TextTestResult):
        def startTest(self,test):
            super().startTest(test)
            if args.progress:print(test.id(),flush=True)
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=1,resultclass=ProgressResult).run(suite)
    from spikes_studio.document import write_json
    from spikes_studio.release_policy import digest
    report=dict(tests=result.testsRun,passed=result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
        failures=[dict(test=t.id(),traceback=message) for t,message in result.failures+result.errors],
        skipped=[dict(test=t.id(),reason=reason) for t,reason in result.skipped],
        native_library_sha256=digest(library),log=output.getvalue(),release_qualification=False)
    write_json(args.output,report)
    print({key:report[key] for key in ('tests','passed','failures','skipped','release_qualification')})
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
