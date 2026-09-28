# SPDX-License-Identifier: Apache-2.0
"""Ask an offline LM Studio or Ollama model to operate SPIKE tools."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.spike_core.local_llm import main


if __name__ == "__main__":
    raise SystemExit(main())
