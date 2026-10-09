# SPIKE Brand Assets

<img src="../app/public/spike-logo.png" alt="SPIKE logo" width="420">

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

- `app/public/spike-logo.png`: horizontal documentation logo.
- `app/public/spike-mark.svg`: raster-backed SVG compatibility wrapper for the
  header, About dialog, and browser favicon; not an editable vector master.
- `app/public/spike-icon.png`: 512px symbol.
- `app/public/favicon.png`: 64px fallback.
- `app/src-tauri/icons/icon.png`, `128x128.png`, `icon.ico`, and `icon.icns`:
  native application, installer, Linux, and macOS assets.
- `kicad_plugin/spike_icon.png`: 48px plugin toolbar icon.

The renderer only crops, pads, and resizes approved artwork; it does not call a
generation service. SPIKES Studio is a separate product and retains its own
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
