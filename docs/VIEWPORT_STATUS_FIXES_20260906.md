# Viewport and status corrections — 2026-09-06

Source follow-up after the archived 0.2.10 installer. Not yet installed or
visually accepted in the native release executable.

- Empty workspaces now show neutral setup guidance, not successful import,
  DC convergence or incomplete-stackup claims. Loaded issue messages follow
  the workspace/analysis. Real incomplete stackup warnings remain actionable.
- Removed unconditional "Contract valid" from the bottom dock; design loading
  and analysis validation are no longer conflated. Warning counts match the
  rendered workspace warnings.
- EM chamber exposes Top/Bottom/Isometric, Orbit/Pan, Fit chamber and Focus DUT.
  Global camera and navigation commands are forwarded to the chamber. Board
  coordinate orbit targets are not misinterpreted as chamber coordinates.
- Camera actions update live camera/controls without reconstructing chamber
  geometry; camera up-vector survives scene changes. DUT focus is unavailable
  without an actual loaded source.
- Board toolbar adds Focus selected. 2D/3D selection bounds or finite position
  fallback center the view with bounded zoom. A large selected plane is not
  cropped to less than its own extent. Changing selection after a focus command
  does not repeatedly recenter the 2D camera.

Verification: all 50 frontend test scripts passed; focused selection/empty-state
and chamber camera tests pass. TypeScript and production frontend build passed.
These checks do not substitute for native visual acceptance. No physics
qualification gates were removed, and no installer was overwritten.
