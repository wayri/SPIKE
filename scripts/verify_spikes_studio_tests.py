"""Run Studio regression tests and retain failures/skips as structured evidence."""
import argparse
import io
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python'),str(ROOT/'.tmp/studio-deps')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--ngspice',type=Path)
    parser.add_argument('--wx',action='store_true',help='Enable opt-in native wx widget tests')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    library=args.library.resolve(strict=True)
    os.environ['SPIKES_TEST_LIBRARY']=str(library);os.environ['SPIKES_TEST_NATIVE_LIBRARY']=str(library)
    if args.ngspice:os.environ['SPIKES_TEST_NGSPICE']=str(args.ngspice.resolve(strict=True))
    if args.wx:os.environ['SPIKES_TEST_WX']='1'
    suite=unittest.defaultTestLoader.discover(str(ROOT/'standalone/spikes_project/tests/python'))
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=1).run(suite)
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
