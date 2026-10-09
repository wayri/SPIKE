# SPDX-License-Identifier: Apache-2.0
"""Render the approved SPIKE raster logo into documentation and platform icons."""
import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/assets/spike-logo-source.png"


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
    render()
