# CP77 Crash Scanner

A desktop tool for diagnosing crashes and mod conflicts in **Cyberpunk 2077**.  
Scans log files from **Mod Organizer 2** and **Vortex**, classifies errors, detects framework versions, and generates a portable crash report.

[![Latest release](https://img.shields.io/github/v/release/dw1rf/CP77CrashScanner?style=for-the-badge&color=9c42ef)](https://github.com/dw1rf/CP77CrashScanner/releases/latest)
[![Download](https://img.shields.io/github/downloads/dw1rf/CP77CrashScanner/total?style=for-the-badge&color=6f2bd9)](https://github.com/dw1rf/CP77CrashScanner/releases)

> Also available on **[Nexus Mods](https://www.nexusmods.com/cyberpunk2077/mods/30924)**
https://github.com/dw1rf/CP77CrashScanner/releases/latest
---
https://github.com/dw1rf/CP77CrashScanner/releases/latest
## Features

- **Auto-scan** on startup if MO2 instance is configured
- **Crash cause detection** — shows the specific mod(s) responsible, not generic hints
- **r6 conflict detection** *(new in 1.2)* — parses `redscript`, `TweakXL` and `ArchiveXL` logs to name mods that overwrite each other's methods/records or reference missing code
- **Framework version check** — RED4ext, CET, ArchiveXL, TweakXL, Codeware, redscript
- **Framework dependency chains** — finds the first missing, failed or incompatible link instead of checking each framework in isolation
- **Failed-to-load tab** — ready-to-share list of incompatible mods
- **Vortex support** — auto-detected, no extra configuration needed
- **Bilingual UI** — Russian / English, switchable at runtime
- **Purge logs** *(new in 1.3)* — one-click delete of all scanned log files and crash dumps, with a yes/no confirmation. Clear stale logs, launch the game to reproduce the crash, then scan a clean set
- **One-file export** — full report with raw logs in a single `.txt`
- **Copy-paste** — all result panels are selectable and copyable

## Supported mod managers

| Manager | Support |
|---------|---------|
| Mod Organizer 2 | ✅ Full (set instance folder) |
| Vortex | ✅ Auto-detected from `%AppData%\Vortex\cyberpunk2077` |
| Manual install | ✅ Set game folder only |

## Screenshot

![Main window](image.webp)

## Requirements

- Windows 10 / 11
- Cyberpunk 2077 (any version with RED4ext recommended)
- No Python required — single portable `.exe`

## Usage

1. Download `CP77CrashScanner.exe` from [Releases](https://github.com/dw1rf/CP77CrashScanner/releases)
2. Run it — auto-scans if your MO2 instance path is already saved
3. Set **MO2 instance** folder and/or **Game** folder
4. Press **SCAN**
5. Review the tabs; use **REPORT TO 1 FILE** to export for sharing

## Tabs

| Tab | What it shows |
|-----|---------------|
| Summary | Error counts, top mods by errors, crash causes with mod names |
| By Mod | All mods grouped with expandable error list |
| Didn't Load ⚠ | Mods that failed to load or compile |
| r6 conflicts ⚔ | Mods overwriting the same method/record + redscript compile errors |
| All Errors | Every unique error/warning, deduped |
| Compatibility | Framework versions, Vortex status, scanned paths |
| Dumps & Logs | Crash dumps and log files with timestamps |

## Crash causes detected

| Cause | Description |
|-------|-------------|
| `redscript compile error` | Script mod won't compile — black screen / freeze on load |
| `RED4ext plugin failed` | DLL mod incompatible with current patch |
| `version mismatch` | Mod built for a different game patch |
| `missing class/method` | Missing framework dependency |
| `engine crash (access violation)` | Archive conflict or corrupted `.archive` |
| `missing .archive` | Incomplete mod installation |
| `NCA: state machine error` | Night City Allies crash in specific locations |

## Mod conflict detection in r6 *(new in 1.2)*

The archive conflict detectors in MO2/Vortex only cover file overwrites in `archive/pc/mod`. They can't see conflicts inside `r6` — those only surface when the `redscript` compiler runs. This tool reads those logs and names the offending mods on the **r6 conflicts ⚔** tab:

| Source | What it catches |
|--------|-----------------|
| `redscript` | Two mods `@replaceMethod`-ing the same method (only one can win) — reports the losing mod and target class |
| `redscript` | Compile errors — missing class/method, unresolved references from an outdated script mod |
| `TweakXL` | Conflicting / redefined records and dependency issues |
| `ArchiveXL` | Missing dependencies and resource conflicts |

Example output: `[CONFLICT] [redscript] quickhacks_sort_by_slot @replaceMethod(RPGManager): this method replacement overwrites a previous annotation…`

> Note: redscript only names the *losing* mod in an override conflict (the one whose replacement was dropped) — the engine does not log the winner. That's still enough to identify the culprit and disable it or fix the load order.

## Configuration

Settings are auto-saved to `scanner_config.json` next to the `.exe`:

```json
{
  "instance": "C:\\MO2\\MO2_Cyberpunk",
  "game": "C:\\Games\\Cyberpunk 2077",
  "lang": "en",
  "recommended": {
    "RED4ext": "1.27.0",
    "Cyber Engine Tweaks": "1.35.0"
  },
  "framework_dependencies": {
    "ArchiveXL": [
      {"name": "RED4ext", "min_version": "1.27.0"},
      {"name": "redscript", "min_version": "0.5.27"}
    ]
  }
}
```

Edit `recommended` to pin versions for your game patch. A component entry in
`framework_dependencies` replaces its built-in dependency list; rules support
`min_version` and optional `max_version`.

## Building from source

Requirements: Python 3.12+, Windows 10/11

```bash
git clone https://github.com/dw1rf/CP77CrashScanner.git
cd CP77CrashScanner
pip install -r requirements.txt
build_windows.bat
```

Output: `dist\CP77CrashScanner\CP77CrashScanner.exe` (onedir build)
Release ZIP: `dist\CP77CrashScanner_v1.4.0.zip`

**Note on antivirus detections:** Release builds use Nuitka standalone mode — no PyInstaller bootloader, UPX compression, obfuscation, or self-extracting installer. Full source code and SHA-256 checksums are included for review. An unsigned executable can still trigger reputation-based warnings; report any false positive to the relevant antivirus vendor.

For code signing: set `WINDOWS_CERT_PFX_BASE64` and `WINDOWS_CERT_PASSWORD` as GitHub Actions secrets. The workflow signs the EXE before generating checksums and the release ZIP.

## License

MIT — free to use, modify, and redistribute.

---

*Made for the Cyberpunk 2077 modding community.*
