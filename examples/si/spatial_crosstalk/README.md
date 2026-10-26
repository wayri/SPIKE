# Sampled SI crosstalk on an original straight pair

This original Apache-2.0 fixture maps computed victim-voltage phasors onto 32
positions on an 80 mm victim stroke. The supplied even/odd RLGC values describe
an assumed uniform symmetric pair. They were **not extracted from this PCB**.
The aggressor is driven with a 1 sqrt(W) RMS incident wave; both victim ports
and the far aggressor port have zero incident waves. All ports use 50 ohms.

1. Reproduce with `.venv/Scripts/python.exe -B examples/si/spatial_crosstalk/build.py`.
2. Load the canonical `design.json` through the desktop canonical source importer.
   In HF / SI, open the S-parameter workspace and expand **Spatial crosstalk
   samples and main viewport**.
3. Select the displayed aggressor/victim identities and request
   `original-spatial-pair-1`. Expand **Solve supplied coupled-line pair**, import
   `solver.json`, then explicitly **Run supplied pair**. Use the 3D main viewport.
   Change frequency, phase/component, opacity and probe point.

Alternatively import `samples.json`, review and admit its binding. This works
only if the current canonical design digest and occurrence still match exactly;
if import normalization changed the source, run the supplied pair on the current
design instead. The example source digest identifies the original declared
fixture descriptor in `build.py`, not a manufactured or measured board.

`setup.json` is the complete `run_si_spatial_pair` worker parameter envelope.
`evidence.json` retains the exact context, supplied request, solved phasors and
limitations. Editing the source invalidates the digest binding. A different
board occurrence requires a new explicit run/binding; renaming a file is not
sufficient. Save the project to retain inputs and unadmitted sample candidates;
reopening requires a current-context bind. Explicit file exports remain
available. Multi-board transformed occurrences are currently unsupported.

The colored samples show actual returned RMS phasor voltage in volts. They do
not show surrounding electric fields, continuous unsampled traces, radiated
interference, thermal effects, protocol pass/fail or measured validation.
No interpolation or artificial distance halo is generated. This is an
experimental visualization/line-model example, not USB or Ethernet compliance.
The governing numerical method and existing reference checks are described in
[the coupled-pair method](../../../docs/RLGC_COUPLED_PAIR.md).
