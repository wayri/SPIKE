"""Frozen-process entry point for the SPIKE local analysis worker."""

import sys


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--extension-host":
        # The trusted extension registry launches a fresh frozen worker as its
        # Python host. A frozen sys.executable is not a general Python CLI.
        import runpy
        from pathlib import Path
        if len(sys.argv) < 3:
            raise SystemExit("Extension host requires an entrypoint.")
        script = Path(sys.argv[2]).resolve()
        if not script.is_file(): raise SystemExit("Extension entrypoint does not exist.")
        sys.argv = [str(script), *sys.argv[3:]]
        runpy.run_path(str(script), run_name="__main__")
    else:
        from python.spike_core.service import main
        raise SystemExit(main())
