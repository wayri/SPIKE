# SPDX-License-Identifier: Apache-2.0
"""Compatibility import for the OpenEMS extension reference evidence."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("extensions.openems_suite.openems_validation_evidence")
