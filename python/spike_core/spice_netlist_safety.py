# SPDX-License-Identifier: Apache-2.0
"""Dependency-free validation shared by visual and external SPICE adapters."""

FORBIDDEN_DIRECTIVES = {
    ".control", ".endc", ".include", ".inc", ".lib", ".load",
    "shell", "source", "cd", "aspice", "codemodel",
}
MAX_NETLIST_BYTES = 10 * 1024 * 1024


def validate_netlist(netlist: str) -> str:
    encoded = netlist.encode("utf-8")
    if not netlist.strip() or len(encoded) > MAX_NETLIST_BYTES:
        raise ValueError("The ngspice netlist is empty or exceeds the 10 MiB limit.")
    for line_number, line in enumerate(netlist.splitlines(), start=1):
        stripped = line.strip().lower()
        if not stripped or stripped.startswith("*"):
            continue
        token = stripped.split(maxsplit=1)[0]
        if token in FORBIDDEN_DIRECTIVES:
            raise ValueError(
                f"Unsafe ngspice directive is not allowed at line {line_number}: {token}"
            )
    lines = netlist.rstrip().splitlines()
    end_index = next(
        (index for index, line in enumerate(lines) if line.strip().lower() == ".end"),
        len(lines),
    )
    if not any("filetype=ascii" in line.lower().replace(" ", "") for line in lines):
        lines.insert(end_index, ".options filetype=ascii")
        end_index += 1
    if end_index == len(lines):
        lines.append(".end")
    return "\n".join(lines) + "\n"
