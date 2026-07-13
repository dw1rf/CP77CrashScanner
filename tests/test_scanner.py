import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cp77_crash_scanner as scanner


class LogClassificationRegressionTests(unittest.TestCase):
    def scan_log(self, relative_path, content):
        with tempfile.TemporaryDirectory() as tmp:
            game_dir = Path(tmp)
            log_path = game_dir / relative_path
            log_path.parent.mkdir(parents=True)
            log_path.write_text(content, encoding="utf-8")

            with mock.patch.object(scanner, "detect_vortex_dir", return_value=None):
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
