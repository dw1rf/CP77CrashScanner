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


if __name__ == "__main__":
    unittest.main()
