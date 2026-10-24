# SPDX-License-Identifier: Apache-2.0
"""CLI registration and dispatch for bounded experimental EM co-simulation."""

from __future__ import annotations

from argparse import _SubParsersAction, Namespace
from pathlib import Path
from typing import Any, Callable


_REQUEST_LIMIT = 8 * 1024**2
_METHODS = {
    "prepare": "prepare_emerge_cosimulation_source",
    "ac": "solve_em_network_ac",
    "resistor-thermal": "run_em_network_resistor_thermal",
    "resistor-cht": "run_em_network_resistor_cht",
    "spice": "run_em_spice_coupling",
    "body-heating": "run_em_body_heating",
}


def register_em_cosimulation_commands(subparsers: _SubParsersAction) -> None:
    group = subparsers.add_parser(
        "em-cosim",
        help="Run bounded experimental EMerge/network/thermal composition",
    )
    commands = group.add_subparsers(dest="em_cosim_command", required=True)
    for name, help_text in (
        ("prepare", "Prepare a bound EMerge sampled-network source"),
        ("ac", "Solve exact supplied-frequency circuit boundaries"),
        ("resistor-thermal", "Map explicit circuit-series-resistor heat to retained cells"),
        ("resistor-cht", "Map explicit circuit-series-resistor heat into retained creeping CHT"),
        ("spice", "Execute bounded linear AC/EM coupling in the owned SPICE engine"),
        ("body-heating", "Calibrate retained E/H volume loss and solve shared-mesh heat"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument(
            "request",
            type=Path,
            help=("JSON containing the six source-preparation fields" if name == "prepare"
                  else "Versioned request JSON"),
        )


def dispatch_em_cosimulation(
    args: Namespace,
    *,
    read_json: Callable[[Path], dict[str, Any]],
    response: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> Any:
    path = args.request
    try:
        size = path.stat().st_size
    except OSError:
        raise
    if size > _REQUEST_LIMIT:
        raise ValueError("EM co-simulation request exceeds 8 MiB.")
    request = read_json(path)
    return response(_METHODS[args.em_cosim_command], {"request": request})["result"]
