# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 dw1rf

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cp77_crash_scanner as scanner


class LogClassificationRegressionTests(unittest.TestCase):
    def scan_log(self, relative_path, content, config=None):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            log_path = game_dir / relative_path
            log_path.parent.mkdir(parents=True)
            log_path.write_text(content, encoding="utf-8")

            with mock.patch.object(scanner, "detect_vortex_dir", return_value=None), \
                    mock.patch.object(scanner, "load_config", return_value=config or {}):
                return scanner.scan("", str(game_dir))

    def test_audioware_negative_status_is_not_an_error(self):
        result = self.scan_log(
            Path("red4ext/logs/audioware-current.log"),
            """[info] initialization complete
no error reported!
no errors detected!
no scene error reported!
""",
        )

        self.assertEqual([], result.findings)

    def test_redscript_location_header_is_not_a_standalone_finding(self):
        result = self.scan_log(
            Path("r6/logs/redscript_rCURRENT.log"),
            """[WARN - Tue, 7 Jul 2026 02:59:43 +0300] At C:\\Game\\r6\\scripts\\quickhacks_sort_by_slot\\quickhacks_sort_by_slot.reds:58:1:
@replaceMethod(RPGManager)
^^^
this method replacement overwrites a previous annotation targeting the same method, only one replacement per method can be active at a time
""",
        )

        self.assertEqual([], result.findings)
        self.assertEqual(1, len(result.conflicts))
        self.assertIn("overwrites a previous annotation", result.conflicts[0].message)

    def test_real_errors_are_still_reported(self):
        result = self.scan_log(
            Path("red4ext/logs/plugin.log"),
            "[error] failed to initialize broken_plugin.dll\n",
        )

        self.assertEqual(1, len(result.findings))
        self.assertEqual("ERROR", result.findings[0].severity)

    def test_success_messages_with_panic_in_mod_name_are_not_errors(self):
        result = self.scan_log(
            Path("bin/x64/cyber_engine_tweaks.log"),
            """mapping file in vfs: C:\\Game\\mods\\No Crowd panic from devices.log, C:\\MO2\\overwrite\\No Crowd panic from devices.log
[2026-07-10 21:40:15] Mod No Crowd panic from devices loaded! ('C:\\Game\\mods\\No Crowd panic from devices')
[2026-07-10 21:40:26] No Crowd panic from devices: 1.2.0 Initialized.
""",
        )

        self.assertEqual([], result.findings)

    def test_real_runtime_panic_is_still_an_error(self):
        result = self.scan_log(
            Path("bin/x64/cyber_engine_tweaks.log"),
            "Lua runtime panic while executing callback\n",
        )

        self.assertEqual(1, len(result.findings))
        self.assertEqual("ERROR", result.findings[0].severity)

    def test_explicit_error_beats_success_message_rule(self):
        result = self.scan_log(
            Path("bin/x64/cyber_engine_tweaks.log"),
            "[error] Mod No Crowd panic from devices loaded!\n",
        )

        self.assertEqual(1, len(result.findings))

    def test_explicit_non_problem_levels_do_not_run_keyword_heuristics(self):
        result = self.scan_log(
            Path("red4ext/logs/plugin.log"),
            """[info] Loading Better Crash Collection
[debug] missing vehicle lookup is expected
[trace] deprecated error callback registered
""",
        )

        self.assertEqual([], result.findings)

    def test_redscript_inventory_path_with_crash_name_is_not_a_finding(self):
        result = self.scan_log(
            Path("r6/logs/redscript_rCURRENT.log"),
            "C:\\Game\\r6\\scripts\\Better Crash Collection\\main.reds\n",
        )

        self.assertEqual([], result.findings)

    def test_untagged_crash_message_remains_an_error(self):
        result = self.scan_log(
            Path("red4ext/logs/plugin.log"),
            "Game crash detected while loading world\n",
        )

        self.assertEqual(1, len(result.findings))
        self.assertEqual("ERROR", result.findings[0].severity)


class ExclusionTests(unittest.TestCase):
    def scan_log(self, relative_path, content, config=None):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            log_path = game_dir / relative_path
            log_path.parent.mkdir(parents=True)
            log_path.write_text(content, encoding="utf-8")

            with mock.patch.object(scanner, "detect_vortex_dir", return_value=None), \
                    mock.patch.object(scanner, "load_config", return_value=config or {}):
                return scanner.scan("", str(game_dir))

    def test_normalization_is_literal_trimmed_casefolded_and_ordered(self):
        exclusions = scanner.normalize_exclusions({
            "sources": ["  Faction Evolved ", "faction evolved", "", 42, "RED4ext"],
            "phrases": [" Vehicle.*Missing ", "vehicle.*missing", None],
        })

        self.assertEqual(["Faction Evolved", "RED4ext"], exclusions["sources"])
        self.assertEqual(["Vehicle.*Missing"], exclusions["phrases"])

    def test_phrase_exclusion_is_case_insensitive_and_does_not_treat_regex_specially(self):
        result = self.scan_log(
            Path("red4ext/logs/plugin.log"),
            """[error] VEHICLE.*MISSING optional record
[error] vehicleZZZmissing is a real failure
""",
            {"exclusions": {"phrases": ["vehicle.*missing"]}},
        )

        self.assertEqual(1, len(result.findings))
        self.assertIn("vehicleZZZmissing", result.findings[0].text)
        self.assertEqual(1, result.excluded_count)
        self.assertEqual(1, result.active_exclusion_rules)

    def test_source_exclusion_matches_resolved_source_case_insensitively(self):
        result = self.scan_log(
            Path("red4ext/logs/faction-evolved.log"),
            "[error] failed to find optional vehicle\n",
            {"exclusions": {"sources": ["RED4EXT: FACTION-EVOLVED"]}},
        )

        self.assertEqual([], result.findings)
        self.assertEqual(1, result.excluded_count)

    def test_excluded_finding_does_not_create_framework_chain_evidence(self):
        result = self.scan_log(
            Path("bin/x64/cyber_engine_tweaks/mods/NoisyMod/noisy.log"),
            "[error] failed to load missing_dependency.dll\n",
            {"exclusions": {"sources": ["noisymod"]}},
        )

        self.assertEqual([], result.findings)
        self.assertFalse(any(
            "NoisyMod" in diagnostic.affected or "missing_dependency" in diagnostic.evidence
            for diagnostic in result.chain_diagnostics
        ))

    def test_malformed_exclusions_are_ignored(self):
        result = self.scan_log(
            Path("red4ext/logs/plugin.log"),
            "[error] failed to initialize broken_plugin.dll\n",
            {"exclusions": "not-an-object"},
        )

        self.assertEqual(1, len(result.findings))
        self.assertEqual(0, result.active_exclusion_rules)

    def test_excluded_redscript_conflict_does_not_reappear(self):
        result = self.scan_log(
            Path("r6/logs/redscript_rCURRENT.log"),
            """[WARN] At C:\\Game\\r6\\scripts\\Crash Sorter\\sort.reds:58:1:
@replaceMethod(RPGManager)
^^^
this method replacement overwrites a previous annotation targeting the same method, only one replacement per method can be active at a time
""",
            {"exclusions": {"sources": ["crash sorter"]}},
        )

        self.assertEqual([], result.conflicts)
        self.assertEqual([], result.findings)
        self.assertGreaterEqual(result.excluded_count, 1)

    def test_version_and_raw_log_survive_phrase_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            log_path = game_dir / "red4ext/logs/red4ext.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                "RED4ext (v1.30.0) is initializing\n[error] harmless optional vehicle missing\n",
                encoding="utf-8",
            )
            config = {"exclusions": {"phrases": ["harmless optional vehicle"]}}
            with mock.patch.object(scanner, "detect_vortex_dir", return_value=None), \
                    mock.patch.object(scanner, "load_config", return_value=config):
                result = scanner.scan("", str(game_dir))

            report = scanner.build_report(result, "", str(game_dir), include_raw=True)

        self.assertEqual("1.30.0", result.versions["RED4ext"])
        self.assertEqual([], result.findings)
        self.assertIn("harmless optional vehicle missing", report)
        self.assertIn("Excluded by custom rules: 1", report)

    def test_save_config_reports_success_and_preserves_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scanner_config.json"
            config = {"lang": "en", "custom": {"keep": True}}
            with mock.patch.object(scanner, "CONFIG_PATH", str(path)):
                self.assertTrue(scanner.save_config(config))
                self.assertEqual(config, scanner.load_config())


class SessionAndConfidenceTests(unittest.TestCase):
    def scan_game(self, game_dir, recent_only=True):
        with mock.patch.object(scanner, "detect_vortex_dir", return_value=None), \
                mock.patch.object(scanner, "load_config", return_value={}):
            return scanner.scan("", str(game_dir), recent_only=recent_only)

    def test_latest_session_excludes_older_log_from_main_diagnosis(self):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            logs = game_dir / "red4ext/logs"
            logs.mkdir(parents=True)
            old_log = logs / "old.log"
            current_log = logs / "current.log"
            old_log.write_text("[error] failed to initialize stale_plugin.dll\n", encoding="utf-8")
            current_log.write_text("[warning] current session warning\n", encoding="utf-8")
            old_time = 1_700_000_000
            os.utime(old_log, (old_time, old_time))
            os.utime(current_log, (old_time + scanner.SESSION_WINDOW_SECONDS + 60,) * 2)

            result = self.scan_game(game_dir)

        self.assertEqual([str(old_log)], [path for path, _ in result.older_log_files])
        self.assertFalse(any("stale_plugin" in finding.text for finding in result.findings))
        self.assertTrue(any("current session" in finding.text for finding in result.findings))

    def test_old_timestamped_block_is_excluded_from_current_append_only_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            log_path = game_dir / "red4ext/logs/plugin.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                "[2026-01-01 10:00:00] [error] failed to initialize stale.dll\n"
                "[2026-08-27 10:00:00] [info] current launch started\n",
                encoding="utf-8",
            )
            current_time = scanner.dt.datetime(2026, 8, 27, 10, 5, 0).timestamp()
            os.utime(log_path, (current_time, current_time))

            result = self.scan_game(game_dir)

        self.assertEqual([], result.findings)

    def test_plain_error_is_not_automatically_a_crash_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            log_path = game_dir / "red4ext/logs/plugin.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("[error] optional runtime record unavailable\n", encoding="utf-8")

            result = self.scan_game(game_dir)

        self.assertEqual("none", result.findings[0].confidence)
        self.assertEqual("unclassified", result.findings[0].relevance)
        self.assertEqual("unclassified", result.diagnosis_state)

    def test_nca_without_temporal_crash_correlation_is_low_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            log_path = game_dir / "red4ext/logs/nca.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("[NCA] error: unexpected spawn state\n", encoding="utf-8")

            result = self.scan_game(game_dir)

        diagnosis = result.problems[0]
        self.assertEqual(("low", "context", False),
                         (diagnosis.confidence, diagnosis.relevance, diagnosis.correlated))
        self.assertEqual("unclassified", result.diagnosis_state)

    def test_nca_near_current_dump_is_medium_possible(self):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            logs = game_dir / "red4ext/logs"
            logs.mkdir(parents=True)
            log_path = logs / "nca.log"
            dump_path = logs / "Cyberpunk2077.dmp"
            log_path.write_text("[NCA] error: unexpected spawn state\n", encoding="utf-8")
            dump_path.write_bytes(b"dump")
            event_time = 1_800_000_000
            os.utime(log_path, (event_time, event_time))
            os.utime(dump_path, (event_time + 30, event_time + 30))

            result = self.scan_game(game_dir)

        diagnosis = result.problems[0]
        self.assertEqual(("medium", "possible", True),
                         (diagnosis.confidence, diagnosis.relevance, diagnosis.correlated))
        self.assertEqual("classified", result.diagnosis_state)

    def test_fresh_dump_without_known_signature_is_unclassified_and_report_is_sendable(self):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            logs = game_dir / "red4ext/logs"
            logs.mkdir(parents=True)
            log_path = logs / "plugin.log"
            dump_path = logs / "Cyberpunk2077.dmp"
            log_path.write_text("[error] unexpected engine shutdown\n", encoding="utf-8")
            dump_path.write_bytes(b"dump")

            result = self.scan_game(game_dir)
            report = scanner.build_report(result, "", str(game_dir), include_raw=True)

        self.assertEqual("unclassified_crash", result.diagnosis_state)
        self.assertIn("ONE-FILE SUPPORT REPORT", report)
        self.assertIn("[UNCLASSIFIED CTD]", report)
        self.assertIn("unexpected engine shutdown", report)
        self.assertIn("RAW LOGS FROM ACTIVE SESSION", report)

    def test_non_russian_system_gets_english_fallback(self):
        with mock.patch.object(scanner.locale, "getlocale", return_value=("de_DE", "UTF-8")):
            self.assertEqual("en", scanner.detect_default_language())
        with mock.patch.object(scanner.locale, "getlocale", return_value=("ru_RU", "UTF-8")):
            self.assertEqual("ru", scanner.detect_default_language())


class ReleaseMetadataTests(unittest.TestCase):
    def test_version_metadata_and_license_are_present(self):
        root = Path(__file__).resolve().parents[1]

        self.assertEqual(scanner.__version__, (root / "version.txt").read_text().strip())
        license_text = (root / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 3, 29 June 2007", license_text)

        icon = (root / "assets/app_icon.ico").read_bytes()
        self.assertEqual(b"\x00\x00\x01\x00", icon[:4])
        self.assertEqual(7, int.from_bytes(icon[4:6], "little"))
        self.assertTrue((root / "assets/app_icon.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_release_builds_include_license_and_source_archive(self):
        root = Path(__file__).resolve().parents[1]
        local_build = (root / "build_windows.bat").read_text(encoding="utf-8-sig")
        nuitka_build = (root / "build_nuitka.bat").read_text(encoding="utf-8-sig")
        workflow = (root / ".github/workflows/build.yml").read_text(encoding="utf-8")
        spec = (root / "CP77CrashScanner.spec").read_text(encoding="utf-8")

        for content in (local_build, workflow):
            self.assertIn("LICENSE", content)
            self.assertIn("CHANGELOG.md", content)
            self.assertIn("_source.zip", content)
        self.assertIn(r"tests\test_scanner.py", local_build)
        self.assertIn("tests/test_scanner.py", workflow)
        for content in (local_build, nuitka_build, workflow):
            self.assertIn("CP77 Crash Scanner.exe", content)
        for content in (nuitka_build, workflow, spec):
            self.assertIn("app_icon.ico", content)


class FrameworkChainTests(unittest.TestCase):
    def test_compatible_chain_is_ok(self):
        result = scanner.evaluate_framework_chains(
            {"RED4ext": "1.30.0", "redscript": "0.5.30", "ArchiveXL": "1.26.0"},
            [],
            {"ArchiveXL": [
                {"name": "RED4ext", "min_version": "1.27.0"},
                {"name": "redscript", "min_version": "0.5.27"},
            ]},
        )

        self.assertEqual([], result.diagnostics)
        self.assertEqual("loaded", result.states["ArchiveXL"].status)

    def test_missing_and_failed_dependencies_are_distinct(self):
        failed = scanner.Finding(
            "RED4ext (loader)", "ERROR", "failed to initialize red4ext.dll",
            False, True, "red4ext.log", 1,
        )
        result = scanner.evaluate_framework_chains(
            {"ArchiveXL": "1.26.0", "TweakXL": "1.11.3"},
            [failed],
            {
                "ArchiveXL": [{"name": "RED4ext"}],
                "TweakXL": [{"name": "redscript"}],
            },
        )

        reasons = {d.root: d.reason for d in result.diagnostics}
        self.assertEqual("load_failed", reasons["RED4ext"])
        self.assertEqual("not_detected", reasons["redscript"])

    def test_unknown_dependency_version_is_insufficient_data(self):
        result = scanner.evaluate_framework_chains(
            {"ArchiveXL": "1.26.0"}, [],
            {"ArchiveXL": [{"name": "RED4ext", "min_version": "1.27.0"}]},
            loaded_frameworks={"RED4ext"},
        )

        self.assertEqual("insufficient_data", result.diagnostics[0].reason)

    def test_incompatible_dependency_is_reported_once_for_multiple_consumers(self):
        result = scanner.evaluate_framework_chains(
            {"RED4ext": "1.20.0", "ArchiveXL": "1.26.0", "TweakXL": "1.11.3"},
            [],
            {
                "ArchiveXL": [{"name": "RED4ext", "min_version": "1.27.0"}],
                "TweakXL": [{"name": "RED4ext", "min_version": "1.27.0"}],
            },
        )

        self.assertEqual(1, len(result.diagnostics))
        self.assertEqual({"ArchiveXL", "TweakXL"}, set(result.diagnostics[0].affected))

    def test_cycle_is_reported_without_recursion(self):
        result = scanner.evaluate_framework_chains(
            {"A": "1.0", "B": "1.0"}, [],
            {"A": [{"name": "B"}], "B": [{"name": "A"}]},
        )

        self.assertTrue(any(d.reason == "invalid_rule" for d in result.diagnostics))

    def test_transitive_chain_reaches_the_root_failure(self):
        result = scanner.evaluate_framework_chains(
            {"A": "1.0", "B": "1.0"}, [],
            {"A": [{"name": "B"}], "B": [{"name": "C"}]},
        )

        diagnostic = next(d for d in result.diagnostics if d.root == "C")
        self.assertIn("A -> B -> C", diagnostic.chains)

    def test_invalid_version_rule_is_reported_without_crashing(self):
        result = scanner.evaluate_framework_chains(
            {"A": "1.0", "B": "1.0"}, [],
            {"A": [{"name": "B", "min_version": "not-a-version"}]},
        )

        self.assertTrue(any(d.reason == "invalid_rule" for d in result.diagnostics))

    def test_report_contains_dependency_chain_section(self):
        result = scanner.ScanResult()
        result.chain_diagnostics.append(scanner.ChainDiagnostic(
            "RED4ext", "not_detected", ["ArchiveXL"],
            ["ArchiveXL -> RED4ext"], ">= 1.27.0", confidence="rule"))

        report = scanner.build_report(result, "", "", include_raw=False)

        self.assertIn("FRAMEWORK DEPENDENCY CHAINS", report)
        self.assertIn("ArchiveXL → RED4ext", report)

    def test_failed_red4ext_plugin_does_not_mark_loader_as_failed(self):
        plugin_failure = scanner.Finding(
            "RED4ext: broken_plugin", "ERROR", "failed to initialize broken_plugin.dll",
            False, True, "plugin.log", 1,
        )
        result = scanner.evaluate_framework_chains(
            {"RED4ext": "1.30.0"}, [plugin_failure], {},
        )

        self.assertEqual("loaded", result.states["RED4ext"].status)


if __name__ == "__main__":
    unittest.main()
