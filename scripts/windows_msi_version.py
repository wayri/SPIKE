# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Version admission only; never installs, repairs, or modifies an MSI."""
import argparse
import json
from pathlib import Path
import re


def application_core(version):
    if not isinstance(version, str):
        raise ValueError("Application version must be a string")
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
        r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?", version)
    if not match:
        raise ValueError("Invalid application semantic version")
    if match[4] and any(p.isdigit() and len(p) > 1 and p.startswith("0") for p in match[4].split(".")):
        raise ValueError("Invalid numeric prerelease identifier")
    return tuple(int(match[i]) for i in (1, 2, 3)), match[4]


def validate_wix_override(application, override):
    core, prerelease = application_core(application)
    if override is None:
        return
    if prerelease:
        raise ValueError("Explicit prerelease MSI mapping requires a separately reviewed policy")
    expected = ".".join(map(str, core))
    if not isinstance(override, str) or override != expected:
        raise ValueError("WiX override must equal the three-component application version; fourth-component ordering is unsupported")


def stable_msi_core(application):
    core, prerelease = application_core(application)
    if prerelease:
        raise ValueError("Prerelease MSI ordering is not defined; do not silently collapse prerelease into stable")
    if core[0] > 255 or core[1] > 255 or core[2] > 65535:
        raise ValueError("Application version exceeds MSI ProductVersion limits")
    return core


def validate_product_version(application, product):
    core = stable_msi_core(application)
    if not isinstance(product, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:\.0)?", product):
        raise ValueError("Malformed MSI ProductVersion or unsupported nonzero fourth component")
    if tuple(map(int, product.split(".")[:3])) != core:
        raise ValueError("Internal MSI ProductVersion differs from application version")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--application", required=True)
    parser.add_argument("--product-version")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if config.get("version") != args.application:
        raise ValueError("Effective Tauri version differs from application version")
    validate_wix_override(args.application, config.get("bundle", {}).get("windows", {}).get("wix", {}).get("version"))
    stable_msi_core(args.application)
    if args.product_version is not None:
        validate_product_version(args.application, args.product_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
