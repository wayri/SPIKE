# SPDX-License-Identifier: Apache-2.0
"""Build and test SPIKE's standalone native cavity kernel using CMake."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build-native-airflow")
    parser.add_argument("--generator")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    command = ["cmake", "-S", str(ROOT / "src/airflow"), "-B", str(args.build_dir), "-DCMAKE_BUILD_TYPE=Release"]
    if args.generator:
        command += ["-G", args.generator]
    subprocess.run(command, check=True)
    subprocess.run(["cmake", "--build", str(args.build_dir), "--config", "Release", "--parallel", "2"], check=True)
    if not args.skip_tests:
        subprocess.run(["ctest", "--test-dir", str(args.build_dir), "-C", "Release", "--output-on-failure"], check=True)

if __name__ == "__main__":
    main()
