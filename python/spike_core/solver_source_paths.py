# SPDX-License-Identifier: Apache-2.0
"""Resolve named implementation sources after the solver package migration.

Used only for existing source-identity inventories, without importing numerical
modules or changing their hash algorithms. The basename remains the record key.
"""
from pathlib import Path


def solver_source_path(name: str) -> Path:
    from .solvers._source_layout import MODULE_FILES

    if not isinstance(name, str) or Path(name).name != name or not name.endswith('.py'):
        raise ValueError('Expected one Python source basename')
    base = Path(__file__).resolve().parent
    return base / MODULE_FILES.get(name, name)
