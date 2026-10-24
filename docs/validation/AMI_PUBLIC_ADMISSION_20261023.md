<!-- SPDX-License-Identifier: Apache-2.0 -->
# Public Windows x64 AMI admission attempt (2026-10-23)

## Outcome

No external vendor or reference AMI binary was executed. The public candidates
found in primary sources did not satisfy the existing SPIKE native-development
admission boundary without an installer, account/form, external source build,
or unreviewed package terms/dependencies. This attempt therefore does **not**
close vendor interoperability or external numerical-comparison evidence.

The gates in `docs/SI_AMI_EXECUTION.md` were preserved: a candidate must provide
an exact Windows AMD64 DLL and matching AMI parameter definition; its origin,
use rights, hash and direct imports must be reviewed before setting the request's
license/dependency acknowledgements. Installers are not model DLLs, and public
downloadability alone is not license approval or trust evidence.

## Bounded local evidence

Evidence is retained only under the ignored directory
`build/ami-public-admission-20261023/`; it is not a release input.

| Artifact | Official source | Bytes | SHA-256 | Inspection and disposition |
| --- | --- | ---: | --- | --- |
| `sprm731.zip` | [TI SPRM731 download endpoint](https://www.ti.com/lit/zip/sprm731), also listed on the [AM2432 product page](https://www.ti.com/product/AM2432) | 45,541,410 | `33b8850262fac8702ad094a16b5897b91d3c672512a67497894e0630153a09e3` | ZIP directory has one 47,699,449-byte member, `SPRM731-1.0-windows-x64-installer.exe`, dated 2021-01-28. The member was extracted as inert data and hashes `22bbddd578e0cf955bf87ad64e5ffa444a60f983d09d2c8474f34fdb0ff09903`; it was never launched. Windows libarchive/tar 10.0.26100.9711 and 7-Zip 26.00 both report the EXE as an unrecognized/not-openable archive. No supported static inner-member listing or selective extraction was therefore possible. |
| `pyibis_ami-9.2.0-py3-none-any.whl` | [PyPI project](https://pypi.org/project/PyIBIS-AMI/) and the author's [upstream repository](https://github.com/capn-freako/PyAMI) | 1,637,105 | `32e19f63841c758b7a0088bc343ecb42f524333983f152b893a77800c4516cff` | Wheel member-name scan found no `.dll`, `.so`, `.ami`, or `.ibs`. Metadata identifies version 9.2.0 and the included license grants BSD-style redistribution, but there is no executable reference model to admit. Nothing was installed or executed. |

The downloaded TI archive is a different revision from the previously recorded
SPRM808 archive (`a1ed6e...b04f6`); both independently terminate at an installer.
Static inspection of an installer container would not itself establish assent,
permission or trust. The outer EXE was extracted only as inert data and offered
to the installed archive reader; because its format was unsupported, no inner
payload or terms were extracted. The installer was not launched and no
installation-time agreement or dependency workflow was bypassed.

The final bounded installer-family check found `C:\Program Files\7-Zip\7z.exe`
even though it is not on `PATH`; forced ZIP and automatic listing both failed.
PE VersionInfo names product `AM64x SERDES IBIS-AMI Model`, company
`Texas Instruments`, file version `1.0.0.0`, product version `1.0`, original
filename `setup.exe`, and `Copyright Texas Instruments`. Windows Authenticode
reports `NotSigned`, so there is no signer or timestamp certificate to bind the
downloaded bytes to a publisher. Targeted ASCII/UTF-16 marker checks found none
of the standard NSIS/Nullsoft, Inno Setup, InstallShield, InstallBuilder,
InstallAnywhere, Advanced Installer, 7z, CAB or RAR signatures. Standard ZIP
local headers do occur inside the EXE, but their bounded filenames identify
only repeated Linux `torrent16ffc_tx_linux.so` and
`torrent16ffc_rx_linux.so` payloads; 7-Zip cannot treat the enclosing format or
those offsets as an archive. No Windows DLL, AMI text, README or terms member
was exposed by this check.

Accordingly there is no identified, suitable installed extraction tool for this
container, and acquiring an unverified extractor would not be an admission-safe
next step. The remaining rights question cannot yet be put as acceptance of a
specific named inner license: TI's named package terms are not statically
available. The owner would first need TI to provide a directly inspectable
archive/license, or explicitly authorize running the installer far enough to
display and preserve its exact terms in a disposable environment; that latter
action remains outside this review and still would not authorize model loading.

## Primary-source candidate review

1. The [IBIS Open Forum test-kit repository](https://github.com/IBIS-Library/IBIS-AMI-test-kits)
   publishes only the Cadence v3.1 and SiSoft v2.21 legacy archives and says
   license information is inside each archive. The prior inspection already
   established that the relevant Cadence Windows model is PE32 machine `0x014c`,
   not the required AMD64 PE. The SiSoft v2.21 kit was separately inspected as
   described below; it is also PE32. No newer Windows x64 binary is published
   there.

2. TI's official [AM64x SerDes IBIS-AMI README](https://www.ti.com/lit/an/spracv3/spracv3.pdf)
   identifies `torrent16_tx_win64.dll` and `torrent16_rx_win64.dll` as 64-bit
   Windows models. The newly inspected corresponding public SPRM731 payload,
   however, exposes only an installer. TI's current
   [online terms](https://www.ti.com/legal/terms-conditions/terms-of-use.html)
   state that downloaded software is governed by accompanying/included license
   terms, or by TI's evaluation software agreement when none accompany it.
   Running or extracting the installer would be required to discover the actual
   model members and package-time terms/dependencies, so this candidate was not
   admitted.

3. The [Analog Devices IBIS model catalog](https://www.analog.com/en/resources/simulation-models/ibis-models.html)
   presents AMI downloads through a personal-details/consent workflow. No form
   was submitted and no consent was given, so no exact binary or license evidence
   was available for admission.

4. Renesas documents multiple Windows x64 AMI DLLs in its official
   [RZ/G3E model application note](https://www.renesas.com/en/document/apn/rzg3e-high-speed-interface-s-parameteribis-ami-model),
   but the [RZ/G3E product page](https://www.renesas.com/en/products/rz-g3e)
   marks the model ZIP "Log in to Download". No account login or new terms were
   accepted, so the exact archive, license and dependency identities remain
   unavailable.

5. The IBIS Open Forum's [tools page](https://ibis.org/tools/tools.htm) points to
   the `ibisami` reference infrastructure, and its upstream repository describes
   Windows x64 build support under a BSD-3-Clause license. It publishes source
   and build instructions rather than a reviewed prebuilt Windows x64 model DLL.
   Building or adapting that external implementation was outside this admission
   attempt and would not constitute execution of a published reference binary.

## SiSoft v2.21 kit discrimination

The official [IBIS Open Forum SiSoft v2.21 archive](https://ibis.org/macromodel_wip/archive/20090930/toddwesterhoff/SiSoft%20IBIS-AMI%20Eval%20Toolkit%20v2.21/SiSoft_IBIS-AMI_Eval_Toolkit_v2.21.zip)
was downloaded as 2,891,903 bytes with SHA-256
`0d16a2188af327683ac419a85ef695af18499808fa9ceda3142028d9cd482d25`.
Its 34 entries total 4,354,768 uncompressed bytes; the largest is 2,253,034
bytes. The static listing contains only directories and regular files, with no
absolute/traversal member or member above 32 MiB. Only `license.txt`,
`readme.txt`, `src/IBIS_AMI_Tx.ami`, `src/sisoft_tx.ibs`, and the prebuilt
`windows/IBIS_AMI_Tx.dll` were extracted into the ignored evidence directory;
source members were not extracted or reviewed.

The DLL is exactly 98,304 bytes and hashes
`beff5daed5d00e1e07fbd51ceda0b3b939179b8988d4e3e8e25a1bbd0c1f104c`.
Direct PE metadata is `MZ`, `PE\0\0`, machine `0x014c` (Intel 386), optional
header magic `0x010b` (PE32), five sections, characteristics `0x2102`. This is
independent evidence that the SiSoft DLL is 32-bit and cannot enter SPIKE's
AMD64-only host; dependency inspection and execution were therefore unnecessary.
The AMI text also lacks the `AMI_Version` declaration required by SPIKE's
existing parameter subset and contains legacy declarations, so static parameter
admission fails before native loading.

The bundled SiSoft terms are named `license.txt`. They state that downloading
and using the toolkit constitutes agreement, then grant use, copying,
modification and distribution for educational, research and commercial purposes
without fee or a signed agreement, subject to preserving specified notices and
all original files in distributions. This inspection records those words; it
does not assert that the owner accepted them or that they authorize a third-party
host run. No SiSoft executable was run. Owner/legal choice would be required
before any otherwise compatible revision could be used under those terms.

## Admission decision and remaining blocker

There is no exact candidate for which all required assertions can truthfully be
made at once: published Windows AMD64 model bytes, matching supported AMI text,
affirmative local-use rights, reviewed dependencies limited to SPIKE's admitted
System32/CRT set, and a model usable without accepting a form or running an
installer. Consequently `license_reviewed: true` and
`dependency_reviewed: true` could not be asserted for any external DLL, and the
existing host/API was intentionally not invoked.

To close the gap, the owner must supply either (a) a vendor package already
obtained under accepted terms containing a standalone Windows x64 DLL and its
matching `.ami`, license, dependency manifest and documented operating inputs,
or (b) an official public archive that exposes the same evidence directly. The
next review must hash the exact members, apply the existing PE/import admission
before loading, preserve the native child/job limits, and compare only against
vendor-published/reference outputs that include explicit inputs and tolerances.
Passing that run would establish bounded ABI interoperability for the exact
model and inputs only; it would not establish physical-device, channel, BER, or
production qualification.
