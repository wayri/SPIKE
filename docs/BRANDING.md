# SPIKE Brand Assets

<img src="../app/public/spike-logo-tagline.png" alt="SPIKE — SI, PI, Thermal, EM" width="420">

## Public tagline

Use **SI, PI, Thermal, EM** in that order, with that capitalization, on
public-facing documentation, presentation covers, demo title cards and
promotional material. Pair it with the SPIKE wordmark. SI means signal
integrity, PI means power integrity, and EM means electromagnetics.

Use `app/public/spike-logo-tagline.png` for slide decks and documents, or
`app/public/spike-logo-tagline.svg` for web layouts. Both have transparent
backgrounds and light blue text suited to dark backgrounds. The SVG retains
the approved raster logo with an accessible, editable text tagline.
Regenerate just these public lockups with
`python scripts/render_brand_assets.py --tagline-only`.
The tagline names analysis domains; retain each solver's existing capability
and validation qualifications alongside technical claims.

The approved 2026-10-10 identity combines an angular PCB-trace S, a signal
spike, and a light blue SPIKE wordmark. Use the horizontal logo for documentation
and the compact symbol for application, plugin, favicon, and project-file icons.

## Source and provenance

`docs/assets/spike-logo-source.png` is the approved transparent raster master
for the symbol. `docs/assets/spike-logo-light-source.png` is the lighter wordmark
revision. Both were generated with OpenAI's built-in image tool at Yawar B's
request. The generation and revision prompts are retained in
`docs/assets/spike-logo-prompt.txt`. No external reference image, third-party
logo, or font file was imported. These project assets are distributed under
SPIKE's Apache-2.0 license; this does not establish trademark clearance.

Run `python scripts/render_brand_assets.py` with Pillow installed to regenerate:

- `app/public/spike-logo.png`: horizontal documentation and application-header logo.
- `app/public/spike-logo-tagline.png` and `spike-logo-tagline.svg`: public
  documentation and presentation lockups with **SI, PI, Thermal, EM**.
- `app/public/spike-mark.svg`: raster-backed SVG compatibility wrapper for the
  About dialog and browser favicon; not an editable vector master.
- `app/public/spike-icon.png`: 512px symbol.
- `app/public/favicon.png`: 64px fallback.
- `app/src-tauri/icons/icon.png`, `128x128.png`, `icon.ico`, and `icon.icns`:
  native application, installer, Linux, and macOS assets.
- `kicad_plugin/spike_icon.png`: 48px plugin toolbar icon.

The renderer crops, pads, and resizes approved artwork and typesets the public
tagline; it does not call a generation service. SPIKES Studio is a separate product and retains its own
identity. Historical screenshots and archived releases retain their original
artwork.

## Project-file icons

Tauri's existing Windows `.spike` association uses the installed executable's
icon. The NSIS association registers `SPIKE Project` with the executable's icon
index 0; replacing `icon.ico` updates that embedded symbol on rebuild. macOS
bundles include `icon.icns`. The Flatpak recipe ships the project MIME definition
and `application-x-spike-project` icon and declares its MIME type in the desktop
entry. Saved project contents and the package format do not change.

Rebuild and install the updated app to update native icons. Previously released
installers do not change when source assets change. Shells may cache icons until
they refresh; file-handler preferences remain under operating-system control.

This is an engineering record, not a legal trademark clearance. Before public commercial release:

1. Search relevant trademark databases in target markets.
2. Check software and hardware icon databases for confusingly similar marks.
3. Register SPIKE's word mark and logo only after clearance.
4. Keep source prompts, generation metadata, and asset hashes with the release record.
5. Do not add third-party logos to SPIKE's UI without permission.

## Solver suite mark

The solver suite uses the single typographic **S** derived from the SPIKE
wordmark, in `app/public/spike-solver-suite.png`. Its transparent square canvas
includes padding for compact and circular placements. The asset was prepared
with an image-editing model using the existing wordmark as its reference.
The Discord server retains the circuit-shaped S in `app/public/spike-icon.png`.
