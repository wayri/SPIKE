# SPIKES standalone project

SPIKES is the standalone circuit-simulation engine, SDK, console, model toolchain,
and desktop workbench extracted from the SPIKE integration repository.
The generated source package is self-contained: it carries the C++ engine,
versioned C ABI, Python orchestration layer, native console/dashboard, tests,
examples, qualified redistributable models, and the SPIKES Studio product plan.

The current version is an unsigned engineering preview. Read `RELEASE_NOTES.md`
and `docs/SOLVER_STATUS.md` before making compatibility, performance, device-
accuracy, hard-real-time, or physical-HIL claims.

## Build the engine

```powershell
cmake -S . -B build -G Ninja -DBUILD_TESTING=ON
cmake --build build
ctest --test-dir build --output-on-failure
python -m unittest discover -s tests/python -v
```

Eigen 3.4 and OpenMP are required. The runnable Studio workbench uses wxPython
(native wxWidgets controls), Matplotlib, and the C++ engine library:

```powershell
python -m pip install ".[studio]"
spikes-studio --library build/spikes_c_api.dll
```

See [the illustrated workbench guide](studio/docs/WORKBENCH_GUIDE.md) for actual
run screenshots, the recorded walkthrough, signal math, properties, probes,
shortcuts, HDL synthesis/timing, library design, and supported interchange.

The planned all-C++ wxWidgets/VTK GUI remains a separate target. This option
currently exposes its architecture/contracts to the build:

```powershell
cmake -S . -B build-studio -DSPIKES_BUILD_STUDIO=ON
```

## Python CLI and model paste

```powershell
python -m python.spikes --help
python -m spikes_studio.model_import --statement ".model DMOD D(Is=2n N=1.2)"
```

The `.MODEL` converter creates a versioned, unreviewed schematic-part record.
It never promotes a pasted vendor card to a qualified or redistributable model.

## Local datasheet assistant

`spikes_studio.local_ai` can form an inert part/model draft with a local LM
Studio or Ollama model. Endpoints are restricted to explicit loopback HTTP URLs;
requests and responses are bounded, and the returned C/SPICE/Verilog-A text is
forced to `unreviewed` and non-executable:

```python
from spikes_studio.local_ai import DatasheetEvidence, LocalModelAssistant, build_formation_request

request = build_formation_request(
    [DatasheetEvidence("opamp-datasheet.pdf", extracted_text, ("p. 5", "p. 17"))],
    intent="Create an op-amp symbol and behavioral SPICE macromodel",
)
draft = LocalModelAssistant().create_draft(
    "ollama", "http://127.0.0.1:11434", "qwen2.5-coder", request
)
```

PDF/OCR/OpenCV extraction is a separate restricted worker planned by the Studio
architecture. The connector accepts its page-addressed observations but does not
execute OCR, download a model, or approve generated source by itself.

The deployment contract at
`studio/schemas/studio-deployment-model-v1.schema.json` defines typed SIL, PIL,
HIL, observer and control-plant packages with explicit clocks, validity envelope,
hash provenance and qualification state.

## Layout

- `engine/src/spikes`: native C++ engine, C ABI, console and dashboard
- `python/spikes`: Python CLI and analysis/model/session layers
- `studio`: GUI contracts, model-paste workflow, and desktop implementation plan
- `studio/library`: toolkit-neutral, standards-traceable symbol geometry
- `models`: redistributable compiled reference models and legal notices
- `tests`: native and Python test corpus
- `docs`: capability boundaries, GUI plan, and evidence

Regenerate this project from the integration repository with
`scripts/build_spikes_standalone_project.py`; do not manually copy build trees.
