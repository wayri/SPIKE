# SPDX-License-Identifier: Apache-2.0
"""Typed geometry-only Gmsh extension entrypoint."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from extension_sdk.python.spike_extension_sdk import read_request, write_result
from python.spike_core.gmsh_extension_runtime import dispatch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    write_result(args.result, dispatch(read_request(args.request)))


if __name__ == '__main__':
    main()
