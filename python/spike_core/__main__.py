"""Run the SPIKE CLI with ``python -m python.spike_core``."""

if __name__ == "__main__":
    from .numerical_runtime import bootstrap_worker_numerics
    bootstrap_worker_numerics()

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
