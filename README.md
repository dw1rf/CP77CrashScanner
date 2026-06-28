# CP77 Crash Scanner

A desktop tool for diagnosing crashes and mod conflicts in **Cyberpunk 2077**.  
Scans log files from **Mod Organizer 2** and **Vortex**, classifies errors, detects framework versions, and generates a portable crash report.

> **[Download latest release →](https://github.com/dw1rf/CP77CrashScanner/releases/latest)**  
> Also available on **[Nexus Mods](https://www.nexusmods.com/cyberpunk2077/mods/30924)**

---

## Features

- **Auto-scan** on startup if MO2 instance is configured
- **Crash cause detection** — shows the specific mod(s) responsible, not generic hints
- **Framework version check** — RED4ext, CET, ArchiveXL, TweakXL, Codeware, redscript
- **Failed-to-load tab** — ready-to-share list of incompatible mods
- **Vortex support** — auto-detected, no extra configuration needed
- **Bilingual UI** — Russian / English, switchable at runtime
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
  }
}
```

Edit the `recommended` block to pin versions for your specific game patch.

## Building from source

```bash
pip install pyinstaller
pyinstaller --noconfirm CP77CrashScanner.spec
# Output: dist/CP77CrashScanner.exe
```

## License

MIT — free to use, modify, and redistribute.

---

*Made for the Cyberpunk 2077 modding community.*
