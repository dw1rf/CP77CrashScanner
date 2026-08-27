# Changelog

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
