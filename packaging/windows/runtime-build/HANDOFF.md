# Frozen Windows payload handoff — 2026-11-02

**Functional installer baseline passes; performance and physical desktop acceptance remain open.** No final installer or release was produced. Main owns integration, packaging and release.

## Integrate these production files

`packaging/windows/`:

- `setup.ps1`: included payload only; no runtime downloads/MSYS2 installation.
- `install-runtime-payload.ps1` (new): manifest/archival SHA checks, bounded entry inspection, ownership-marked staging and atomic promotion; flat-payload recovery remains supported.
- `payload-io.cs` (new): batched .NET validation/copy/uninstall; Windows-native archive extraction baseline. Not a bundled development environment.
- `runtime-manifest.ps1`: inventories verified receipt entries rather than adopting unknown files.
- `install.ps1`: stage app and write uninstall manifest before promotion; managed mode does not incorporate external tool directories; includes uninstall helper.
- `uninstall.ps1`: validate all paths before deletion; remove only matching hashes, clear ReadOnly only after hash match, retain unknown/modified files and data.
- `common.ps1`: installed OpenSSL provider directory.
- `Install MediaDesk.cmd`, `README.md`.

Tests: `test-payload.ps1`, `test-archive.ps1`. Existing `doctor.py`, `start.ps1`, `test-install.ps1` remain required. `prepare-runtime.ps1` / `prepare-vlc.ps1` are superseded development experiments: do not expose them as the user install path. Release allowlist must exclude `runtime-build/`, tests, compilers, pacman, headers/static libraries and the MSYS2 environment.

Build helpers under `runtime-build/`: `stage-runtime.py`, `assemble-runtime.py`, `make-payload-archive.py`, `check-pe.py`, `smoke-runtime.py`, `validate-runtime.py`, `run-app-tests.py`, `python-packages.json`. `playback-probe.py` is a non-gate diagnostic with known cleanup failure. `experiments/payload-io-immediate-readback.cs` is the stopped performance experiment, not product code.

## Exact inputs on Windows

SSH: `pc@172.16.18.162` with the already-authorized task key. All paths below start at `C:\Users\pc\AppData\Local\Temp\`:

| Input | Relative path |
| --- | --- |
| Validated build UCRT prefix | `mediadesk-win-gtk-om_0lexo\msys64\ucrt64` |
| Signed Python package extraction incl yt-dlp launcher | `md-runtime-online-20261102\msys64\runtime-package-stage\ucrt64` |
| Official complete VLC source | `md-vlc-official-20261102\vlc-3.0.24` |
| Official Node source | `md-tool-candidates-20261102\node-v24.22.2-win-x64` |
| Gyan full-shared source | `md-tool-candidates-20261102\ffmpeg-9.0.2-full_build-shared` |
| Correct fresh assembled runtime | `md-runtime-fresh-fixed-20261102` |
| Verified ZIP + receipt + file manifest | `md-runtime-archive-20261102` |
| Windows test app/source snapshot | `mediadesk-win-native-dev-20261102` |

The original first fresh target lacked yt-dlp.exe and was correctly rejected before installation. Do not use `md-runtime-fresh-20261102`; use the corrected `fresh-fixed` target.

Correct payload: **12,857 files / 729,678,675 bytes** (695.88 MiB, excluding inventory JSON). ZIP: **312,726,251 bytes** (298.24 MiB).

- ZIP SHA256: `c4fddd482914b4b20cb6718587e9c95508a35563a706e964c82e3808b473317d`
- File manifest SHA256: `5fbf7a67725a1cd519fba873bafcc0e4c2ee111001693d5252e414146ce0d45b`
- Native sources and individual package hashes/licenses: `README.md` and `python-packages.json` in this directory.

The older 185,309,204-byte tar.xz size probe contains a different manual sample with pyc caches; it is not the corrected payload or an installer.

## Build and test commands

Use the validated build Python. Pass the input directories from the table:

```powershell
python -B assemble-runtime.py --ucrt <ucrt> --python-overlay <overlay> --vlc <vlc> --node <node> --ffmpeg <full-shared> --target <fresh-runtime>
python -B make-payload-archive.py --payload <fresh-runtime> --target <fresh-archive-folder>
python -B check-pe.py <fresh-runtime>
python -B smoke-runtime.py <fresh-runtime>
python -B validate-runtime.py --root <fresh-runtime> --app <current-source> --doctor <doctor.py>
python -B run-app-tests.py <fresh-runtime> <windows-test-source>
```

On Windows with a complete source tree and its packaging scripts:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <source>\packaging\windows\test-payload.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File <source>\packaging\windows\test-archive.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File <source>\packaging\windows\setup.ps1 -SourceRoot <source> -PayloadRoot <archive-folder> -InstallRoot <new-case>\app -RuntimeRoot <new-case>\runtime -ShortcutRoot <new-case>\shortcuts
powershell -NoProfile -ExecutionPolicy Bypass -File <new-case>\app\start.ps1 -CheckOnly
powershell -NoProfile -ExecutionPolicy Bypass -File <new-case>\app\uninstall.ps1
```

Use isolated `LOCALAPPDATA`/`APPDATA`, Windows-only PATH, and a synthetic user-data sentinel. Invoke PowerShell by its full System32 path when testing a deliberately restricted PATH. Do not repeat the test harness mistake of treating a missing `powershell` command's stale LASTEXITCODE as a successful uninstall.

## Measured results and limits

Same final directory and 12,857-file payload:

| Mode | Extraction/copy | Target checks | Total setup |
| --- | ---: | ---: | ---: |
| Flat .NET copy | 245.65 s incl immediate target checks | included | 270.76 s |
| Windows tar ZIP baseline | 15.89 s | 207.15 s | 251.74 s |
| One immediate-readback attempt | stopped after improvement condition failed | not complete | not accepted |

Source archive checks were 0.74 + 0.68 seconds. Complete baseline uninstall: **16.65 seconds**; app, private runtime and shortcut all absent, synthetic user-data string still `must-retain`. KeepRuntime app uninstall: 0.96 seconds, runtime retained. A ReadOnly file initially blocked full deletion; fix was validated by resuming safely and by the subsequent complete baseline uninstall.

Latest full baseline log: `%TEMP%\MediaDesk-setup-20261102-121340.log`. Case: `%TEMP%\md-payload-fast-install-5dfdf924824049f18e664ff83bed0cbb`. The later stopped experiment leaves only its `runtime.partial`; no final app/runtime was promoted. That partial and all original caches were retained. No background package download or benchmark process was left running by this worker.

Other passing evidence:

- `md-runtime-evidence-2__ya3zd`: full H.264/HEVC/VP9/AV1 strict decode/probe/cover/preview, AAC merge, truncated-file refusal, byte-exact localhost yt-dlp download after ffplay exclusion.
- `md-portable-app-tests-gmalsfup`: real app setup/workspace/settings/library/Player HWND; Playing/time=3650ms; all five download/resume/process-state regressions.
- Installed-path SVG decoder succeeded; loaded libgtk/librsvg DLLs were inside the new private runtime. Missing-GTK deliberate failure then restored success passed.
- 630 PE files including plugins/native Python modules had no unresolved ordinary/delayed imports; dynamic loads still require scenario tests.
- Archive security tests: SHA corruption before staging, path traversal and link rejection; exact extraction hashes and clean uninstall.

One ordered comparison on one machine; caches were not reset. Do not promote extraction-only time into end-to-end installation performance. Do not assert antivirus was the root cause. No module/locale resource-container compatibility change was made. Physical desktop video/sound, GPU behavior, online extraction, real Google OAuth/accounts, current main-source equivalence and final installer/update/registration need independent main verification. The original UCRT build inputs still need a reproducible frozen package receipt before release.
