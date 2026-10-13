"""Frozen-process entry point for the SPIKE local analysis worker."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str] | None = None) -> int:
    """Dispatch a frozen worker mode while retaining service mode by default."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "--cluster":
        from python.spike_core.cluster_cli import main as cluster_main
        return cluster_main(arguments[1:])
    if arguments == ["--parallel-child"]:
        from python.spike_core.parallel_child import main as parallel_main
        return parallel_main()
    if arguments and arguments[0] == "--cli":
        from python.spike_cli import main as cli_main
        return cli_main(arguments[1:])
    if arguments and arguments[0] == "--mcp":
        from python.spike_core.mcp_server import serve
        serve()
        return 0
    if arguments and arguments[0] == "--local-chat":
        from python.spike_core.local_llm import main
        return main(arguments[1:])
    if arguments and arguments[0] == "--extension-host":
        # The trusted extension registry launches a fresh frozen worker as its
        # Python host. A frozen sys.executable is not a general Python CLI.
        import runpy
        if len(arguments) < 2:
            raise SystemExit("Extension host requires an entrypoint.")
        script = Path(arguments[1]).resolve()
        if not script.is_file(): raise SystemExit("Extension entrypoint does not exist.")
        sys.argv = [str(script), *arguments[2:]]
        runpy.run_path(str(script), run_name="__main__")
        return 0
    from python.spike_core.service import main as service_main
    return service_main()


if __name__ == "__main__":
    raise SystemExit(main())
