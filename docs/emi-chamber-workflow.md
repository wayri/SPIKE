# EMI chamber workspace

Open **EMI** to view the virtual chamber. It contains an absorber-lined shielded room, removable floor absorbers, a turntable, a nonconductive table, a log-periodic receive antenna and mast, and a receiver rack with coax routing. Cutaway removes the front, entry wall and ceiling to expose the DUT.

The chamber copies visible geometry from the board/assembly viewport. It retains imported enclosure meshes, board geometry and assembly offsets. Additional boards retain their existing viewport representations; a board represented there by a proxy remains a proxy in the chamber. Model loading failures and proxy use are identified in the scene caption.

**Auto-place DUT** centers the complete visible device on the table, with its lowest point touching the tabletop. Flat, upright and side orientations and turntable azimuth apply one rigid transform to the whole device. The source assembly is not edited or rescaled. The table expands to accommodate larger devices. **Inspect DUT** fits the camera to the device at its real scale; **Fit chamber** restores a room overview.

Chamber dimensions and controls persist in `emi.setup.chamber` in the existing project package. Older projects receive default settings. **Board / ports setup** returns to the electrical viewport for net and excitation editing; **Chamber** returns to the room.

**Prepare scan** uses the existing assembly-admission and openEMS preparation route. The selected distance is also supplied as the NF2FF observation radius. The scene distance is measured horizontally from the displayed DUT edge; the NF2FF result radius is measured from the solver phase center and is labeled independently in the dashboard. A changed setup requires preparation again before execution.

**Results dashboard** supports a split view alongside the chamber or a full tab. Completed NF2FF data provides a logarithmic frequency spectrum of peak total electric field in dBµV/m, a selectable frequency table with peak angles, a theta/phi field map, a directivity polar cut, integrated radiated power and validation status. Zero fields are identified as zero rather than assigned an arbitrary finite decibel value. Input arrays are checked for shape, finite values and sample budget before display.

## Physics boundary

The chamber and its antenna, absorber, floor, table, height, polarization and device pose controls are a **visual test setup**. They are not a chamber electromagnetic mesh. The existing openEMS adapter solves the prepared electrical domain and computes NF2FF data. It does not simulate receive-antenna transfer functions, absorber properties, receiver detectors, or chamber reflections. Full-wave assembly execution remains subject to the existing backend capability gate; displaying several boards or a STEP-derived enclosure does not bypass it. This change does not add a full multi-board/enclosure chamber solver or compliance certification.

The control vocabulary follows the usual separation of antenna height, polarization and turntable azimuth described in the [Rohde & Schwarz ES-K1 field-strength test manual](https://scdn.rohde-schwarz.com/ur/pws/dl_downloads/dl_common_library/dl_manuals/dl_user_manual/ES-K1_Manual_en_08.pdf). It is not a claim that the default dimensions implement any specific test standard.

## Verification

- `cd app; npm run test:emi-chamber`
- `cd app; npm run test:project`
- `cd app; npm run test:viewport`
- `python -m unittest discover -s tests/python -p test_emi_workflow.py -v`
- `python -m unittest discover -s tests/python -p test_openems_far_field.py -v`
- `cd app; npm run build`
