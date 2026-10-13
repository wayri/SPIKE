# SPDX-License-Identifier: Apache-2.0
"""Render the approved SPIKE raster logo into documentation and platform icons."""
import base64
import argparse
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/assets/spike-logo-source.png"
TAGLINE = "SI, PI, Thermal, EM"


def render_tagline_assets():
    """Export a public lockup while preserving the approved compact identity."""
    path = ROOT / "app/public/spike-logo.png"
    with Image.open(path) as source:
        lockup = source.convert("RGBA")
    fonts = (Path("C:/Windows/Fonts/segoeui.ttf"),
             Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    font_path = next((p for p in fonts if p.is_file()), None)
    font = ImageFont.truetype(str(font_path), 80) if font_path else ImageFont.load_default(size=80)
    ImageDraw.Draw(lockup).text((525, 420), TAGLINE, font=font, fill="#a9d4e9")
    lockup.save(ROOT / "app/public/spike-logo-tagline.png")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    (ROOT / "app/public/spike-logo-tagline.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1805" height="522" viewBox="0 0 1805 522" role="img">'
        '<title>SPIKE — SI, PI, Thermal, EM</title>'
        f'<image width="1805" height="522" href="data:image/png;base64,{data}"/>'
        '<text x="525" y="490" font-family="Segoe UI, DejaVu Sans, sans-serif" font-size="80" fill="#a9d4e9">'
        f'{TAGLINE}</text></svg>\n', encoding="utf-8")


def render():
    with Image.open(SOURCE) as source:
        source = source.convert("RGBA")
        # Fixed bounds isolate the approved symbol, excluding the wordmark.
        mark = source.crop((218, 128, 643, 594))
        icon = Image.new("RGBA", (512, 512))
        mark.thumbnail((448, 448), Image.Resampling.LANCZOS)
        icon.alpha_composite(mark, ((512 - mark.width) // 2, (512 - mark.height) // 2))
        with Image.open(ROOT / "docs/assets/spike-logo-light-source.png") as light:
            light.crop((190, 100, 1995, 622)).save(ROOT / "app/public/spike-logo.png")
        for relative, size in (("app/public/spike-icon.png", 512),
                               ("app/public/favicon.png", 64),
                               ("app/src-tauri/icons/icon.png", 512),
                               ("app/src-tauri/icons/128x128.png", 128),
                               ("kicad_plugin/spike_icon.png", 48)):
            path = ROOT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            icon.resize((size, size), Image.Resampling.LANCZOS).save(path)
        icon.save(ROOT / "app/src-tauri/icons/icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
        icon.resize((1024, 1024), Image.Resampling.LANCZOS).save(ROOT / "app/src-tauri/icons/icon.icns")
        buffer = BytesIO()
        icon.save(buffer, format="PNG")
        data = base64.b64encode(buffer.getvalue()).decode("ascii")
        # Preserve existing SVG consumers; the approved master is raster artwork.
        (ROOT / "app/public/spike-mark.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
            f'<image width="512" height="512" href="data:image/png;base64,{data}"/></svg>\n',
            encoding="ascii")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tagline-only", action="store_true", help="Export public logo lockups without regenerating icons")
    args = parser.parse_args()
    if not args.tagline_only:
        render()
    render_tagline_assets()
