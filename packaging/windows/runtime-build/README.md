# Build-only portable runtime experiment

This directory is for the release builder. Do not ship MSYS2/pacman or run these scripts on an end user's machine. The older `setup.ps1` / `prepare-runtime.ps1` online-MS​YS2 proposal is superseded; it is not the final installation route.

## Verified sample and boundary

Windows sample: `C:\Users\pc\AppData\Local\Temp\md-portable-runtime-20261102`.

- Python/GTK core staged from the existing validated UCRT64 development installation: 172,244,796 bytes before supplemental modules, versus 809,060,112 bytes in that development prefix. Excludes headers, static archives, GIR developer XML, development documentation and unused helper programs. Keeps every runtime DLL, typelib, loader, theme/schema/font/translation and license. `lib/**/*.dll` includes OpenSSL providers; `OPENSSL_MODULES` must point into the installed runtime.
- Runtime-only Gyan FFmpeg 9.0.2 full-shared: `ffmpeg.exe`, `ffprobe.exe`, all accompanying DLLs and root license/readme files, 241,603,358 bytes. `ffplay.exe` excluded and all synthetic format checks rerun successfully.
- Official Node 24.22.2: `node.exe` plus `LICENSE`, 94,083,179 bytes. No npm, headers, installers or development tools.
- Official VLC 3.0.24: all plugins retained. Only SDK/MSI development resources excluded; sample 197,100,259 bytes.
- Google OAuth/requests/EJS dependencies: `python-packages.json` records package versions, URLs, SHA256 and licenses. Those archives passed repository SHA256 checks and detached signature verification with the MSYS2 public keyring from the existing official base. Signer fingerprint `5F944B027F7FE2091985AA2EFA11531AA0AA7F57`. The isolated verification homedir did not configure local ownertrust, so GPG printed "untrusted key" despite a cryptographically valid signature; provenance is the official base public keyring, not a newly accepted arbitrary key.
- yt-dlp 2026.10.26 uses the signed MSYS2 package's native launcher and matching Python module. It works with the portable interpreter under a clean PATH; not the external PyInstaller yt-dlp.exe.

The currently exercised sample totals 769,396,648 bytes in its directories plus inventory JSON (about 733.75 MiB). This includes 39,717,440 bytes of package/test `.pyc` caches; the reusable assembler skips them. All `.mo` translations total 89,817,487 bytes; they were retained. This is a measured intermediate runtime, not a final installer size or a claimed absolute minimum.

## Verified upstream artifacts

| Input | Fixed source | SHA256 |
| --- | --- | --- |
| VLC | `https://download.videolan.org/pub/videolan/vlc/3.0.24/win64/vlc-3.0.24-win64.7z` | `1ed59c09152e78aff84663fa76efab26057716576db74332858810e5ef54ae1f` |
| FFmpeg full-shared | `https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-full_build-shared.7z` | `4d2060a8b34a940aa47d785142055bb92a63053781e55f2ace4546edd519a8f5` |
| FFmpeg essentials comparison only | `https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.7z` | `4705843ccaaf54257c16ad90f3e952ece33c17df964ecf7bfdbb0f49c7171077` |
| Node | `https://nodejs.org/dist/v24.22.2/node-v24.22.2-win-x64.zip` | `ca1bff5d8ead13c9f2ea404a176db46bd430704d5b5113734049fa365e7799e2` |

Checksums came from the same publishers' `.sha256` files / Node `SHASUMS256.txt`. Gyan's primary server stalled and was stopped at 90 seconds; its official GitHub release completed and matched the primary checksum. FFmpeg full-shared is a GPL build; keep its exact `-version`/`-L` evidence and licensing/source obligations for distribution. VLC includes mixed-license plugins; the complete distribution is not collectively LGPL. Node's LICENSE includes bundled third-party notices. The build still needs a frozen receipt for the original UCRT64 base packages; the generated per-file SHA256 inventory makes the current input contents reviewable but is not a complete rebuild lock.

## Reusable scripts

Run with the validated UCRT64 build interpreter. All targets must be fresh directories; source trees are read-only.

```powershell
python assemble-runtime.py --ucrt <validated-ucrt64-prefix> `
  --python-overlay <verified-package-extraction-ucrt64> `
  --vlc <extracted-vlc-3.0.24> --node <extracted-node-v24.22.2-win-x64> `
  --ffmpeg <extracted-ffmpeg-9.0.2-full_build-shared> --target <new-runtime-root>
python check-pe.py <new-runtime-root>
python smoke-runtime.py <new-runtime-root>
python validate-runtime.py --root <new-runtime-root> --app <source-tree> --doctor <doctor.py>
python run-app-tests.py <new-runtime-root> <windows-test-source-tree>
```

`assemble-runtime.py` composes inputs and generates an exact file/size/hash inventory. The consolidated assembler completed on a fresh target `md-runtime-fresh-20261102`: 12,856 files, 729,589,924 bytes before inventory JSON. Its exact inputs are recorded in the generated inventory. Installer integration uses this fresh target. `stage-runtime.py` retains native DLLs broadly rather than guessing which ctypes/GI/plugin loads will occur. `check-pe.py` checks ordinary and delayed imports; dynamically loaded files still require the smoke tests.

`smoke-runtime.py` first hides the candidate GTK DLL, verifies a fresh child fails with a missing-library diagnostic, restores it in `finally`, then creates/realizes/destroys a GTK window. Child interpreter and `sys.prefix` point into the candidate, and PATH contains only candidate bin and Windows System32. This passed, including the deliberate failure case, with 29 pixbuf formats reported.

`validate-runtime.py` runs doctor, captures full capability listings, generates H.264/HEVC/VP9/AV1 synthetic fixtures, strictly decodes/probes/extracts covers and previews, merges AAC, rejects a half-truncated MP4 and performs a byte-exact real yt-dlp localhost HTTP download. `--fixtures-from` reuses the full-build fixtures for paired comparisons. All tests passed after removing ffplay. Evidence: Windows TEMP `md-runtime-evidence-2__ya3zd`; original fixtures and full capability lists: `md-runtime-evidence-i0nnoxrc`.

`run-app-tests.py` creates a new synthetic state directory and calls the existing application and five Windows download regressions with clean PATH and candidate dependencies. Passed: application setup/workspace/settings/library/Player HWND, state Playing and time 3650ms; interrupted/range-resume download, dropped connection, denied/retry, strict truncated-file retry, pause/resume database-failure process-state restoration. Evidence: Windows TEMP `md-portable-app-tests-gmalsfup`.

`playback-probe.py` is a diagnostic, not a passing gate: it decoded four frames to Ended, then its independent ctypes cleanup access-violated. Application smoke exited normally. This diagnostic needs correction or exclusion; do not present it as a clean lifecycle test.

## Essentials comparison

Essentials' ffmpeg+ffprobe total 210,644,992 bytes, saving only 30,958,366 bytes against full-shared without ffplay. The same H.264/HEVC/VP9/AV1 fixtures passed decoding, probing, covers/previews, merging and truncation checks. Nevertheless capabilities drop: decoders 555→542 (including loss of libdav1d, libjxl, libdavs2, libuavs3d), encoders 242→222, demuxers 373→371 (dvdvideo/libmodplug), protocols 44→42 (bluray/rist). AV1 remains available through the native decoder, but 4K performance was not measured. Keep full-shared per the integration decision. Comparison evidence: Windows TEMP `md-runtime-evidence-pgc3w_nx`.

## Required integration and remaining checks

- Replace the superseded end-user MSYS2 download path with a built payload; end users must not receive pacman, headers/static libraries or a compiler/toolchain.
- Adapt app launcher/config to the portable `bin`, `vlc/plugins`, `tools/ffmpeg/bin`, `tools/node` paths and `OPENSSL_MODULES=runtime/lib/ossl-modules`; preserve independent `python.exe`/`pythonw.exe` because OAuth/yt-dlp subprocess paths use `sys.executable`.
- The fresh-target assembly has passed. Complete all gates after installation to a second path to verify relocation and loader/cache paths. Add successful SVG loader instantiation/loaded-module provenance, not only a pixbuf format count.
- Create the real app installer, ownership/uninstall manifests and shortcuts, test install/update/uninstall and modified/unknown-file retention. This directory does not deliver a final installer.
- SSH graphics produced monitor/D3D/OpenGL diagnostics despite app state/time progression. Physical desktop video, sound, GPU paths, real online extraction and real Google OAuth/account flows remain unverified; tests only used synthetic state and local fixtures.
- PE scans do not exhaust GTK/VLC plugin combinations, delayed ctypes paths or every media format. Existing Windows download test coverage is stronger than a simple import check, but does not establish all format/platform behavior.

## Updated installer integration

`setup.ps1` now installs only the included `runtime-payload`; it never invokes MSYS2 preparation. `install-runtime-payload.ps1` checks the archive SHA and entry safety, requires native extraction success, rejects extracted reparse paths, and checks required component presence/length before promotion. It does not hash every newly extracted file. The expanded-directory path retains source/copy SHA checks and matching-ownership resume; reusing an existing runtime still requires all-file SHA verification. `runtime-manifest.ps1 -PayloadReceipt` preserves the original payload hashes for uninstall, so unknown or changed on-disk contents are not adopted for deletion. `install.ps1` stages app files and writes an uninstall manifest before moving to the final app path. `common.ps1` adds the installed OpenSSL provider path. Full fresh-payload install/uninstall testing is in progress; do not mark final packaging complete from source alone.

The older working sample compressed with tar.xz to 185,309,204 bytes (about 176.72 MiB), including package/test pyc caches. This is a size probe, not a distributable installer. The clean fresh-target payload is smaller uncompressed; its final installer compression must be measured separately.

## Frozen handoff status

See [HANDOFF.md](HANDOFF.md) and [performance-evidence.json](performance-evidence.json). The corrected assembler was rerun from a fresh target and includes the signed yt-dlp launcher: 12,857 files / 729,678,675 bytes before inventory JSON. The preferred transfer artifact is one ZIP plus its receipt; this does not change the installed file set.

The tested functional baseline uses Windows `System32/tar.exe`, after locked-archive SHA and complete entry preflight, followed by all-file target SHA. Complete install/installed doctor/full uninstall passed, including user-data preservation and removal of app/runtime/shortcut. It still took 251.74 seconds, so performance is not accepted.

One additional immediate-readback experiment did not meet its predeclared improvement condition and was terminated. Its code is isolated under `experiments/`, never called by setup. The production helper was restored to the complete tested functional baseline. No further optimization was attempted. The interrupted experiment's owned `.partial` directory was retained; no final runtime/app was promoted and the data sentinel remained unchanged.

No Python-module or locale resource-container change was made: compatibility was not established, and the authorized comparison stopped after one failed follow-up. The reason for slow target reads remains unresolved; do not state it was proved to be antivirus or disk behavior.

## QR matrix dependency overlay

`qr-packages.json` pins official PyPI wheels for qrcode 8.2 and its Windows metadata dependency colorama 0.4.6. Download those exact input URLs and retain the pinned SHA256 receipts. `stage-qr-dependencies.py --wheel-dir <verified-wheel-directory> --target <owned-build-staging-directory>` checks both complete wheels before writing only package files, distribution metadata and original license texts. It does not run pip, setup/build hooks or network operations. qrcode includes BSD-3-Clause terms and an inherited MIT notice; preserve the complete LICENSE. colorama is BSD-3-Clause. Pillow and pypng extras are excluded.

`assemble-runtime.py` now requires `--qr-wheels` and stages this overlay before creating its final all-file receipt. When adding it to an already assembled, task-owned build input, regenerate `runtime-files.json` and then `runtime.zip` / `runtime-archive.json`; otherwise the new files are not in the install inventory. Never target an installed user runtime. `check-qr-dependencies.py <overlay-or-staged-runtime>` checks module origins and creates a synthetic 41x41 matrix with PIL/png unavailable. It does not open user login data.

Ubuntu uses the distribution `python3-qrcode` package (noble 7.4.2-4 tested). Its apt dependencies include Pillow/pypng/typing-extensions even though MediaDesk draws only the in-memory matrix with GTK/Cairo.
