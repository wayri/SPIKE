# Engineering reports

The desktop report command produces a self-contained HTML document for the
active engineering discipline. Power-integrity, signal-integrity, and thermal
reports have separate titles, summaries, result language, and setup content.
PI-only electrical analytics and PDN material are omitted from SI and thermal
reports. EMI setup and field sections appear only when the active analysis is
explicitly classified as EMI; merely having an EMI setup in the project does
not add it to a PI, SI, or thermal report.

When several result records are attached, the HTML preview presents one tab per
analyzed net or scope. Each panel retains the result's analysis ID, model status,
returned field range, and exact structured solver provenance. Tabs are a screen
navigation aid only. Print and Save PDF reveal every panel and place the nets in
source order in one document.

The board and result previews use the report's bundled canvas runtime. They do
not require a network connection, a CDN, or Plotly. Surface previews use only
explicit `vertices_mm` faces returned with scalar samples. Shared-edge vertex
values can smooth those faces, but the renderer does not create an implicit
rectangular grid or bridge missing copper, nets, layers, or disconnected faces.
Hover labels report the source solver sample. Rendering is capped at 12,000
triangles, while solver summaries, model status, issues, and provenance remain
authoritative. Missing quantities say `Not returned` and are never coerced to
zero or inferred from another discipline.

Run the focused checks from `app`:

```powershell
npm.cmd run test:report-runtime
npm.cmd exec tsc -- --noEmit
```

For browser review, run the Vite development server and open
`http://127.0.0.1:5187/fixtures/engineering-report-tabs-preview.html`. The page
calls `buildEngineeringReport` with labeled synthetic input; it is UI fixture
data, not solver evidence. Check that net tabs replace the board and graph data,
that the two separated source faces remain separated in contour mode, and that
print preview includes both net panels and their static plots sequentially.
