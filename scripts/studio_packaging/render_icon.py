"""Deterministically render the editable SVG app mark into platform icon assets."""
from pathlib import Path
import shutil
import wx
import wx.svg
from PIL import Image

root=Path(__file__).resolve().parent
app=wx.App(False)
svg=wx.svg.SVGimage.CreateFromFile(str(root/'spikes-studio.svg'))
svg.ConvertToScaledBitmap(wx.Size(512,512)).SaveFile(str(root/'spikes-studio.png'),wx.BITMAP_TYPE_PNG)
with Image.open(root/'spikes-studio.png') as picture:
    picture.save(root/'spikes-studio.ico',format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
target=root.parents[1]/'standalone/spikes_project/studio/library'
if target.is_dir():
    for name in ('spikes-studio.svg','spikes-studio.png','spikes-studio.ico'):shutil.copy2(root/name,target/name)
print(root/'spikes-studio.ico')
