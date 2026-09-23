"""Command-line entry point for the first SPIKES netlist workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from .contracts import ProbeDescriptor
from .netlist import NetlistParseError, parse_netlist
from .native_abi import NativeABIError
from .version import ENGINE_VERSION


CLI_VERSION = ENGINE_VERSION
EXIT_OK = 0
EXIT_INPUT = 2
EXIT_SOLVE = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spikes",
        description="Strict CLI for the experimental SPIKES linear RLC circuit kernel.",
    )
    parser.add_argument("--version", action="version", version=f"SPIKES {CLI_VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)
    loop=commands.add_parser('loop-gain',help='Linear voltage-injection return ratio for an explicitly chosen unilateral loop fixture.')
    loop.add_argument('netlist',type=Path);loop.add_argument('--injection',required=True);loop.add_argument('--assume-unilateral',action='store_true')
    loop.add_argument('--start-hz',type=float,default=1.);loop.add_argument('--stop-hz',type=float,default=1e6);loop.add_argument('--points',type=int,default=301);loop.add_argument('-o','--output',type=Path)
    tfra=commands.add_parser('transient-fra',help='Native sine-injection transfer measurement on a switching-capable deck.')
    tfra.add_argument('netlist',type=Path);tfra.add_argument('--library',required=True);tfra.add_argument('--source',required=True);tfra.add_argument('--output-probe',required=True)
    tfra.add_argument('--frequency-hz',type=float,action='append',required=True);tfra.add_argument('--amplitude',type=float,default=.01);tfra.add_argument('--max-step-s',type=float,default=1e-5)
    tfra.add_argument('-o','--output',type=Path)
    fra = commands.add_parser('fra',help='Explicit linear frequency-response analysis (not switching loop gain).')
    fra.add_argument('netlist',type=Path);fra.add_argument('--source',required=True);fra.add_argument('--output-probe',required=True)
    fra.add_argument('--start-hz',type=float,default=1.);fra.add_argument('--stop-hz',type=float,default=1e6);fra.add_argument('--points',type=int,default=301)
    fra.add_argument('-o','--output',type=Path)
    mixed = commands.add_parser('library-inspect', help='Check a mixed-library manifest and payload hashes without executing code.')
    mixed.add_argument('manifest', type=Path)
    mixed.add_argument('-o', '--output', type=Path)
    for name, help_text in (
        ("check", "Parse and validate a supported SPICE netlist."),
        ("compile", "Emit the normalized project and native request template."),
        ("run", "Run .op, a linear single-source .dc sweep, or a bounded .tran."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("netlist", type=Path)
        command.add_argument(
            "--probe",
            action="append",
            default=[],
            metavar="EXPR",
            help="Add V(node), V(node,node), I(element), or P(element); repeatable.",
        )
        command.add_argument("-o", "--output", type=Path, help="Write JSON to this file instead of stdout.")

    native_run = commands.add_parser(
        "native-run",
        help="Run .op, .dc, or .tran through an explicitly selected owned SPIKES library.",
    )
    native_run.add_argument("netlist", type=Path)
    native_run.add_argument("--library", type=Path, required=True)
    native_run.add_argument(
        "--method",
        choices=("trap", "be", "bdf2"),
        default="trap",
        help=(
            "Transient integration: event-aware hybrid trapezoidal (trap, "
            "default), backward Euler (be), or variable-step BDF2 (bdf2)."
        ),
    )
    native_run.add_argument("--probe", action="append", default=[], metavar="EXPR")
    native_run.add_argument("-o", "--output", type=Path)

    for name, help_text in (
        ("ac", "Run a bounded linear complex AC sweep with an explicit source."),
        ("transfer", "Run AC and reduce one output probe to a transfer function."),
    ):
        frequency = commands.add_parser(name, help=help_text)
        frequency.add_argument("netlist", type=Path)
        frequency.add_argument("--source", required=True, help="Independent voltage or current source ID.")
        frequency.add_argument("--start-hz", type=float, required=True)
        frequency.add_argument("--stop-hz", type=float, required=True)
        frequency.add_argument("--points", type=int, default=101)
        frequency.add_argument("--scale", choices=("linear", "log"), default="log")
        frequency.add_argument("--magnitude", type=float, default=1.0)
        frequency.add_argument("--phase-deg", type=float, default=0.0)
        if name == "ac":
            frequency.add_argument(
                "--probe", action="append", default=[], metavar="EXPR",
                help="Add a complex V(...), I(...), or P(...) series; repeatable.",
            )
        else:
            frequency.add_argument(
                "--output-probe", required=True, metavar="EXPR",
                help="Output V(...) or I(...) divided by the source phasor.",
            )
        frequency.add_argument("-o", "--output", type=Path)

    fourier = commands.add_parser(
        "fourier",
        help="Reduce a completed uniform transient result over integral cycles.",
    )
    fourier.add_argument("result", type=Path, help="JSON output from `spikes run` transient analysis.")
    fourier.add_argument("--probe", required=True, metavar="EXPR")
    fourier.add_argument("--fundamental-hz", type=float, required=True)
    fourier.add_argument("--harmonics", type=int, default=10)
    fourier.add_argument("-o", "--output", type=Path)

    temperature = commands.add_parser(
        "temp-sweep",
        help="Run explicit linear R/L/C temperature-coefficient cases.",
    )
    temperature.add_argument("netlist", type=Path)
    temperature.add_argument("--start-c", type=float, required=True)
    temperature.add_argument("--stop-c", type=float, required=True)
    temperature.add_argument("--step-c", type=float, required=True)
    temperature.add_argument("--reference-c", type=float, default=27.0)
    temperature.add_argument("--tempco", action="append", default=[], metavar="ELEMENT=TC1", required=True)
    temperature.add_argument("--tempco2", action="append", default=[], metavar="ELEMENT=TC2")
    temperature.add_argument("--probe", action="append", default=[], metavar="EXPR")
    temperature.add_argument("-o", "--output", type=Path)

    monte_carlo = commands.add_parser(
        "monte-carlo",
        help="Run deterministic seeded relative-value samples.",
    )
    monte_carlo.add_argument("netlist", type=Path)
    monte_carlo.add_argument("--vary", action="append", default=[], metavar="ELEMENT=TOLERANCE", required=True)
    monte_carlo.add_argument("--samples", type=int, required=True)
    monte_carlo.add_argument("--seed", type=int, required=True)
    monte_carlo.add_argument("--distribution", choices=("uniform", "normal_3sigma_clipped"), default="uniform")
    monte_carlo.add_argument("--probe", action="append", default=[], metavar="EXPR")
    monte_carlo.add_argument("-o", "--output", type=Path)

    corners = commands.add_parser(
        "corner-sweep",
        help="Run every bounded low/high Cartesian relative-value corner.",
    )
    corners.add_argument("netlist", type=Path)
    corners.add_argument("--vary", action="append", default=[], metavar="ELEMENT=TOLERANCE", required=True)
    corners.add_argument("--probe", action="append", default=[], metavar="EXPR")
    corners.add_argument("-o", "--output", type=Path)

    library = commands.add_parser("library", help="Search, inspect, validate, or elaborate built-in archetypes.")
    library_commands = library.add_subparsers(dest="library_command", required=True)
    library_search = library_commands.add_parser("search", help="Search archetype metadata.")
    library_search.add_argument("query", nargs="?", default="")
    library_search.add_argument("--status", choices=("all", "runnable", "unavailable"), default="all")
    library_search.add_argument("-o", "--output", type=Path)
    library_inspect = library_commands.add_parser("inspect", help="Inspect one fully qualified archetype ID.")
    library_inspect.add_argument("archetype_id")
    library_inspect.add_argument("-o", "--output", type=Path)
    library_validate = library_commands.add_parser("validate", help="Validate every runnable built-in elaboration.")
    library_validate.add_argument("-o", "--output", type=Path)
    library_elaborate = library_commands.add_parser("elaborate", help="Elaborate one runnable archetype to native elements.")
    library_elaborate.add_argument("archetype_id")
    library_elaborate.add_argument("--instance", required=True)
    library_elaborate.add_argument("--pin", action="append", default=[], metavar="PIN=NODE", required=True)
    library_elaborate.add_argument("--preset")
    library_elaborate.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    library_elaborate.add_argument("-o", "--output", type=Path)

    benchmark = commands.add_parser("benchmark", help="Run accuracy-gated analytical DC micro-benchmarks.")
    benchmark.add_argument("--warmups", type=int, default=2)
    benchmark.add_argument("--repetitions", type=int, default=7)
    benchmark.add_argument("--timeout", type=float, default=30.0)
    benchmark.add_argument("--external-id")
    benchmark.add_argument("-o", "--output", type=Path)
    benchmark.add_argument(
        "--external-command",
        nargs=argparse.REMAINDER,
        metavar="ARGV",
        help="External JSON wrapper argv; place this option last. No shell is used.",
    )
    capabilities = commands.add_parser('capabilities', help='Run representative parser probes; not a parity or numerical qualification claim.')
    capabilities.add_argument('-o','--output',type=Path)
    qualification = commands.add_parser(
        "qualification",
        help="Run native analytical, switching, interaction, and soft-real-time gates.",
    )
    qualification.add_argument("--library", type=Path, required=True)
    qualification.add_argument("--repetitions", type=int, default=3)
    qualification.add_argument("--wall-steps", type=int, default=20)
    qualification.add_argument("-o", "--output", type=Path)
    return parser


def _emit(value: Any, output: Path | None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output is None:
        sys.stdout.write(rendered)
    else:
        output.write_text(rendered, encoding="utf-8")


def _emit_error(value: Any, output: Path | None) -> None:
    """Prefer the requested sink, but preserve a diagnostic if that sink fails."""

    try:
        _emit(value, output)
    except OSError as exc:
        fallback = dict(value)
        fallback["output_error"] = str(exc)
        _emit(fallback, None)


def _load(path: Path, raw_probes: list[str], *, native_extensions: bool = False):
    if not path.is_file():
        raise OSError(f"Netlist does not exist: {path}")
    probes = tuple(ProbeDescriptor.parse(item) for item in raw_probes)
    return parse_netlist(
        path.read_text(encoding="utf-8"), source_name=str(path), probes=probes,
        native_extensions=native_extensions,
    )


def _assignments(values: list[str], *, numeric: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Expected NAME=VALUE, received {value!r}.")
        name, raw = value.split("=", 1)
        name = name.strip()
        raw = raw.strip()
        if not name or not raw or name in result:
            raise ValueError(f"Assignment {value!r} is empty or duplicated.")
        result[name] = float(raw) if numeric else raw
    return result


def _run_library(arguments: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    from .library import BUILTIN_LIBRARY
    if arguments.library_command == "search":
        matches = BUILTIN_LIBRARY.search(arguments.query, status=arguments.status)
        return EXIT_OK, {
            "contract": "spikes/archetype-search/v1",
            "query": arguments.query,
            "status_filter": arguments.status,
            "count": len(matches),
            "results": [item.to_summary_dict() for item in matches],
        }
    if arguments.library_command == "inspect":
        return EXIT_OK, BUILTIN_LIBRARY.inspect(arguments.archetype_id).to_dict()
    if arguments.library_command == "validate":
        validation = BUILTIN_LIBRARY.validate()
        return (EXIT_OK if validation["valid"] else EXIT_INPUT), validation
    elaborated = BUILTIN_LIBRARY.elaborate(
        arguments.archetype_id,
        arguments.instance,
        _assignments(arguments.pin, numeric=False),
        preset=arguments.preset,
        overrides=_assignments(arguments.param, numeric=True),
    )
    return EXIT_OK, elaborated


def _run_benchmark(arguments: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    from .benchmark import ExternalJsonCommandAdapter, NativeDcAdapter, run_benchmark_suite

    command = tuple(arguments.external_command or ())
    if bool(command) != bool(arguments.external_id):
        raise ValueError("--external-id and --external-command must be supplied together.")
    adapter = (
        ExternalJsonCommandAdapter(arguments.external_id, command, timeout_s=arguments.timeout)
        if command else NativeDcAdapter()
    )
    report = run_benchmark_suite(adapter, warmups=arguments.warmups, repetitions=arguments.repetitions)
    return (EXIT_OK if report["status"] == "passed" else EXIT_SOLVE), report


def main(argv: Iterable[str] | None = None) -> int:
    arguments = _parser().parse_args(list(argv) if argv is not None else None)
    error_output = arguments.output
    try:
        if arguments.command=='loop-gain':
            from .loop_gain import analyze
            result=analyze(arguments.netlist.read_text(encoding='utf-8'),arguments.injection,arguments.start_hz,arguments.stop_hz,arguments.points,assume_unilateral=arguments.assume_unilateral)
            _emit(result,arguments.output);return EXIT_OK
        if arguments.command=='transient-fra':
            from .transient_fra import analyze
            result=analyze(arguments.netlist.read_text(encoding='utf-8'),arguments.library,arguments.source,arguments.output_probe,arguments.frequency_hz,amplitude=arguments.amplitude,max_step_s=arguments.max_step_s)
            _emit(result,arguments.output);return EXIT_OK
        if arguments.command == 'fra':
            from .fra import analyze
            result=analyze(arguments.netlist.read_text(encoding='utf-8'),arguments.source,arguments.output_probe,arguments.start_hz,arguments.stop_hz,arguments.points)
            _emit(result,arguments.output)
            return EXIT_OK if result['status']=='completed' else EXIT_SOLVE
        if arguments.command == 'library-inspect':
            from .mixed_library import inspect_library
            _emit(inspect_library(arguments.manifest), arguments.output)
            return EXIT_OK
        if arguments.command == "library":
            code, payload = _run_library(arguments)
            _emit(payload, arguments.output)
            return code
        if arguments.command == "benchmark":
            code, payload = _run_benchmark(arguments)
            _emit(payload, arguments.output)
            return code
        if arguments.command == 'capabilities':
            from .capability_audit import run_capability_audit
            report=run_capability_audit();_emit(report,arguments.output)
            return EXIT_OK if report['summary']['strict_rejection_sentinels_passed'] else EXIT_SOLVE
        if arguments.command == "qualification":
            from .qualification import run_qualification_suite

            report = run_qualification_suite(
                arguments.library,
                repetitions=arguments.repetitions,
                wall_steps=arguments.wall_steps,
            )
            _emit(report, arguments.output)
            return EXIT_OK if report["status"] == "passed" else EXIT_SOLVE
        if arguments.command == "fourier":
            from .analyses import MAX_FOURIER_RESULT_BYTES, reduce_fourier_result
            if not arguments.result.is_file():
                raise OSError(f"Result does not exist: {arguments.result}")
            if arguments.result.stat().st_size > MAX_FOURIER_RESULT_BYTES:
                raise ValueError(
                    f"Fourier input must not exceed {MAX_FOURIER_RESULT_BYTES} bytes."
                )
            if arguments.output is not None and arguments.output.resolve() == arguments.result.resolve():
                error_output = None
                raise ValueError("Output path must not overwrite the input result.")
            source_result = json.loads(arguments.result.read_text(encoding="utf-8"))
            if not isinstance(source_result, dict):
                raise ValueError("Fourier input JSON must contain one result object.")
            reduced = reduce_fourier_result(
                source_result,
                arguments.probe,
                arguments.fundamental_hz,
                arguments.harmonics,
            )
            _emit(reduced, arguments.output)
            return EXIT_OK
        if arguments.output is not None and arguments.output.resolve() == arguments.netlist.resolve():
            error_output = None
            raise ValueError("Output path must not overwrite the input netlist.")
        if (
            arguments.command == "native-run"
            and arguments.output is not None
            and arguments.output.resolve() == arguments.library.resolve()
        ):
            error_output = None
            raise ValueError("Output path must not overwrite the native library.")
        raw_probes = arguments.probe if arguments.command != "transfer" else [arguments.output_probe]
        project = _load(
            arguments.netlist, raw_probes,
            native_extensions=arguments.command == "native-run",
        )
        if arguments.command in {"temp-sweep", "monte-carlo", "corner-sweep"}:
            from .sweeps import (RelativeVariation, TemperatureCoefficient,
                                 run_corner_sweep, run_monte_carlo, run_temperature_sweep)
            if arguments.command == "temp-sweep":
                raw_linear = _assignments(arguments.tempco, numeric=True)
                raw_quadratic = _assignments(arguments.tempco2, numeric=True)
                linear = {name.upper(): value for name, value in raw_linear.items()}
                quadratic = {name.upper(): value for name, value in raw_quadratic.items()}
                if len(linear) != len(raw_linear) or len(quadratic) != len(raw_quadratic):
                    raise ValueError("Temperature coefficient element IDs must be unique ignoring case.")
                coefficients = tuple(
                    TemperatureCoefficient(name, linear.get(name, 0.0), quadratic.get(name, 0.0))
                    for name in dict.fromkeys((*linear, *quadratic))
                )
                result = run_temperature_sweep(
                    project,
                    arguments.start_c,
                    arguments.stop_c,
                    arguments.step_c,
                    coefficients,
                    reference_c=arguments.reference_c,
                )
            else:
                variation_values = _assignments(arguments.vary, numeric=True)
                variations = tuple(
                    RelativeVariation(name, value)
                    for name, value in variation_values.items()
                )
                result = (
                    run_monte_carlo(
                        project,
                        variations,
                        samples=arguments.samples,
                        seed=arguments.seed,
                        distribution=arguments.distribution,
                    )
                    if arguments.command == "monte-carlo"
                    else run_corner_sweep(project, variations)
                )
            _emit(result, arguments.output)
            return EXIT_OK if result["status"] == "completed" else EXIT_SOLVE
        if arguments.command in {"ac", "transfer"}:
            from .analyses import AcSweep, AcExcitation, run_ac_analysis, run_transfer_function
            sweep = AcSweep(
                start_hz=arguments.start_hz,
                stop_hz=arguments.stop_hz,
                points=arguments.points,
                scale=arguments.scale,
            )
            excitation = AcExcitation(
                source=arguments.source,
                magnitude=arguments.magnitude,
                phase_deg=arguments.phase_deg,
            )
            if arguments.command == "ac":
                result = run_ac_analysis(project, sweep, excitation)
            else:
                result = run_transfer_function(
                    project,
                    sweep,
                    excitation,
                    project.probes[0],
                )
            _emit(result, arguments.output)
            return EXIT_OK if result["status"] == "completed" else EXIT_SOLVE
        if arguments.command == "native-run":
            from .native_runner import run_native_project

            method = {
                "trap": "hybrid_trapezoidal",
                "be": "backward_euler",
                "bdf2": "bdf2",
            }[arguments.method]
            result = run_native_project(
                project, arguments.library, integration_method=method
            ).to_dict()
            _emit(result, arguments.output)
            return EXIT_OK if result["status"] == "completed" else EXIT_SOLVE
        from .runner import compile_project, run_project
        compiled = compile_project(project)
        if arguments.command == "check":
            payload = {
                "contract": "spikes/netlist-check/v1",
                "status": "valid" if compiled["validation"]["valid"] else "invalid",
                "project": project.to_dict(),
                "validation": compiled["validation"],
            }
            _emit(payload, arguments.output)
            return EXIT_OK if compiled["validation"]["valid"] else EXIT_INPUT
        if arguments.command == "compile":
            _emit(compiled, arguments.output)
            return EXIT_OK if compiled["status"] == "ready" else EXIT_INPUT
        result = run_project(project).to_dict()
        _emit(result, arguments.output)
        return EXIT_OK if result["status"] == "completed" else EXIT_SOLVE
    except NetlistParseError as exc:
        _emit_error({"contract": "spikes/cli-error/v1", "status": "error", "issues": [exc.to_dict()]}, error_output)
        return EXIT_INPUT
    except NativeABIError as exc:
        issue = {
            "code": "SPIKES_NATIVE_ABI_ERROR",
            "severity": "error",
            "message": str(exc),
            "path": str(getattr(arguments, "library", "")),
        }
        _emit_error(
            {"contract": "spikes/cli-error/v1", "status": "error", "issues": [issue]},
            error_output,
        )
        return EXIT_SOLVE
    except (OSError, UnicodeError, ValueError) as exc:
        issue = {
            "code": "SPIKES_CLI_INPUT_INVALID",
            "severity": "error",
            "message": str(exc),
            "path": str(getattr(arguments, "netlist", "")),
        }
        _emit_error({"contract": "spikes/cli-error/v1", "status": "error", "issues": [issue]}, error_output)
        return EXIT_INPUT


__all__ = ["CLI_VERSION", "EXIT_INPUT", "EXIT_OK", "EXIT_SOLVE", "main"]
