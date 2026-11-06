# Changelog

## 1.7.2 - 2026-11-06

### Added

- Automatic discovery of Cyberpunk2077 and Cyberpunk2077-* report folders in `%LOCALAPPDATA%\REDEngine\ReportQueue`, without MO2, Vortex, or a configured game folder.
- ReportQueue `.log`/`.txt` logs and `.dmp` inventory in session selection and the one-file Support Report.
- Purge support for these logs and dumps; other games' report folders are excluded.
- Regression coverage for ReportQueue discovery, latest-session selection, purge boundaries, and game version 2.5 parsing.

### Compatibility

- No game-patch gate is imposed by the scanner. Parsing a 2.5 version string is tested; in-game compatibility with patch 2.5 has not been verified.
- Binary dump contents are not decoded. Missing or inaccessible ReportQueue folders are skipped.
- Source packages now include all regression test modules.

## 1.6.0 - 2026-08-27

### Added

- Session-aware scanning that selects the latest two-hour artifact window by default in the GUI and CLI.
- Timestamp-aware filtering for append-only RED4ext, CET, and redscript logs.
- Independent crash-confidence and CTD-relevance labels for every classified diagnostic.
- Temporal dump correlation for NCA companion state-machine messages.
- Honest `UNCLASSIFIED CTD` state when a current crash signal or dump has no known signature.
- One-file Support Report with scanner version, session boundaries, confidence-ranked evidence, dump inventory, excluded-old-log manifest, and active raw logs.
- Automatic first-run language choice: Russian for Russian system locales, English fallback everywhere else.
- Original generated application artwork, embedded as a multi-resolution Windows icon.

### Changed

- NCA state-machine errors are low-confidence context without a correlated dump and medium-confidence possible causes when correlated.
- A source log's `ERROR` level no longer implies that the line is a crash cause.
- The latest-session option is enabled by default while the full-history scan remains available as an explicit override.
- Export naming and UI copy now tell users exactly which single file to send for support.
- The executable is now named `CP77 Crash Scanner.exe` for a clearer Windows presentation.

### Compatibility

- Existing exclusions, framework-chain diagnostics, MO2/Vortex discovery, and the compact tabbed GUI remain supported.
