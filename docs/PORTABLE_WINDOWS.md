# SPIKE Portable Windows Build

Run `spike-desktop.exe` from this directory. Keep the `bundled`, `python`, and
manifest files beside the executable; they are part of the application runtime.

This build does not write a SPIKE installation into Windows. It therefore does
not register the `.spike` file association or Start Menu entry. Use the NSIS
installer for those operating-system integrations.

The desktop workflow is offline after Microsoft WebView2 is available. Current
Windows 10 and Windows 11 installations normally provide WebView2. This alpha
package does not yet include a fixed WebView2 runtime, code signing, or clean-VM
qualification.

The included numerical worker has passed its packaging smoke gates and the
permanent ten-case regression corpus. That packaging result does not promote an
Approximate solver to Validated. Check the model status and validity metadata in
every analysis result and report.
