# Saved simulation sequences

Open Simulation → Manager (Ctrl+J). Set a name and analysis in the profile editor. Create a named sequence and use Add current profile. Repeat for each analysis; profiles are copied, so later editor changes do not silently alter saved entries. Load entry into editor and Replace from editor explicitly updates a saved entry.

Remove, Up/Down and Enable/disable organize the sequence. Run selected executes that entry even if disabled; Run all enabled executes enabled entries in order. Each sequence supports 32 finite batch entries, and a schematic stores up to 32 sequences. Edits are undoable and saved in .spksch.

At run time choose a parent output folder. A unique subfolder stores the sequence manifest, effective per-entry netlists and separate JSON result files. Runs use a fixed project snapshot and independent fresh solver states, not state handoff. Latest results use the existing plot display; prior results remain in the archive, not in an unbounded in-memory list. History records link each capture archive.

Stop cancels the active worker and clears the remaining queue. A failed solver or archive write stops the sequence. Closing the application must not dispatch further entries. Validation checks every enabled netlist before dispatch; backend-specific failures can still occur during solving.

Supported profile choices are operating point, transient and from-netlist (including supported DC/step decks). AC/PZ use the separate frequency panel and are not yet sequence entries. Noise, Monte Carlo and other specialized orchestration are not yet integrated here. Continuous execution is intentionally rejected because it has no automatic end. There is no parallel dispatch, pause/resume for finite batch workers or dependent state transfer in this first implementation.

Native OP → transient execution, order, separate archives and unchanged project source were verified in artifacts/studio-native-sequences-20260906. The installed beta.2 does not automatically include this development change.
