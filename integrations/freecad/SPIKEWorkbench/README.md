# SPIKE companion workbench 0.2.0

Copy this entire `SPIKEWorkbench` folder into FreeCAD's user `Mod` directory,
restart FreeCAD and select **SPIKE ECAD/MCAD**. Find the user directory with
`App.getUserAppDataDir()` in FreeCAD's Python console. This source companion
was tested headlessly with FreeCAD 1.1.3 on Windows.

In a SPIKE build containing FreeCAD collaboration, export a session from
**MCAD assembly > Board instances and harnesses > FreeCAD collaboration**.
Open it using **SPIKE > Open SPIKE Collaboration Session**. Edit the placement
or label of occurrence containers, preserving their geometry children and tree
hierarchy. Save as FCStd to resume later.

Select two solid occurrences and choose **Measure SPIKE Solid Clearance** for
minimum separation and overlap volume. **Send Placement Feedback to SPIKE** saves
a JSON file for SPIKE's review/apply workflow. Placement changes invalidate earlier
measurements. Origin-only objects have no solid to measure.

Board solids represent the supplied outline/thickness; components, copper,
pad/via drills and flex bends are omitted. Check the declared board datum and
export diagnostics. This is not a thermal/structural/electrical solver or a
manufacturing clearance qualification. No runtime or solver is downloaded.

Other commands retain primitive geometry import, envelope/keepout export and
new-part assembly export. Added/deleted/reparented or reshaped session objects
cannot return through placement feedback. Use **Export SPIKE Assembly** for a
separate assembly import of new geometry.
