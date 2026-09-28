# SPDX-License-Identifier: Apache-2.0
"""Compatibility import for the OpenEMS extension case integrity checks."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("extensions.openems_suite.openems_case_integrity")
