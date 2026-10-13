# Result screenshots

Use **Reports > Save result screenshot** to save the currently visible 2D or 3D
board/assembly viewport and its rendered result overlays. Choose WebP or JPEG
for lossy compressed images (quality 90%), or PNG for lossless compression.
Show the desired result and frame before exporting. The image uses the existing
viewport capture path, fitted into 1600 x 1000 pixels. It does not include side
panels or numerical datasets; save the `.spike` project to retain those.

Exports use a timestamped filename and the existing browser/WebView download
workflow. Repeated export is disabled during capture. Capture/codec errors
appear in the status bar. If WebP/JPEG is unsupported, choose PNG; SPIKE rejects
a silent codec fallback rather than saving PNG bytes with the wrong extension.
The encoder allows at most 4 megapixels and releases its canvas backing storage
when encoding finishes or fails. Screenshot compression may alter fine text and
colors; use PNG when preserving exact displayed pixels matters.
