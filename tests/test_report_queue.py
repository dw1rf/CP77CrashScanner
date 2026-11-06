# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 dw1rf

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cp77_crash_scanner as scanner


class ReportQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local = Path(self.tmp.name)
        self.queue = self.local / "REDEngine" / "ReportQueue"
        for patcher in (
            mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)}),
            mock.patch.object(scanner, "detect_vortex_dir", return_value=None),
            mock.patch.object(scanner, "load_config", return_value={}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def artifact(self, folder, name, content=b"dump", timestamp=None):
        path = self.queue / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if timestamp is not None:
            os.utime(path, (timestamp, timestamp))
        return str(path)

    def test_reports_without_game_or_mod_manager_appear_in_support_report(self):
        dump = self.artifact("Cyberpunk2077-2026-11-06", "minidump.dmp")
        log = self.artifact("Cyberpunk2077-2026-11-06", "stacktrace.txt",
                            b"Error reason: EXCEPTION_ACCESS_VIOLATION\n")
        result = scanner.scan("", "", recent_only=True)
        report = scanner.build_report(result, "", "", include_raw=True)
        self.assertEqual([dump], [item[0] for item in result.session_dumps])
        self.assertIn(log, [item[0] for item in result.log_files])
        self.assertIn(dump, report)
        self.assertIn("Error reason: EXCEPTION_ACCESS_VIOLATION", report)

    def test_latest_session_ignores_old_reports_and_other_games(self):
        old = self.artifact("Cyberpunk2077-old", "minidump.dmp", timestamp=100000)
        current = self.artifact("cyberpunk2077-current", "minidump.dmp", timestamp=200000)
        self.artifact("OtherGame-new", "minidump.dmp", timestamp=300000)
        result = scanner.scan("", "", recent_only=True)
        self.assertEqual([current], [item[0] for item in result.session_dumps])
        self.assertEqual({old, current}, {item[0] for item in result.dumps})
        self.assertEqual("unclassified_crash", result.diagnosis_state)

    def test_purge_only_deletes_supported_files_in_cyberpunk_reports(self):
        dump = self.artifact("Cyberpunk2077-current", "minidump.dmp")
        log = self.artifact("Cyberpunk2077-current", "stacktrace.txt", b"trace")
        other = self.artifact("OtherGame-current", "minidump.dmp")
        prefix = self.artifact("Cyberpunk2077Other-current", "minidump.dmp")
        metadata = self.artifact("Cyberpunk2077-current", "report.json", b"{}")
        self.assertEqual({dump, log}, set(scanner.collect_purge_targets("", "")))
        deleted, _, errors = scanner.purge_logs("", "")
        self.assertEqual(2, deleted)
        self.assertEqual([], errors)
        for path in (other, prefix, metadata):
            self.assertTrue(Path(path).exists())

    def test_missing_queue_or_environment_does_not_scan_relative_paths(self):
        self.assertEqual([], scanner.collect_scan_dirs("", ""))
        self.artifact("Cyberpunk2077-current", "minidump.dmp")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": ""}):
            self.assertEqual([], scanner.collect_scan_dirs("", ""))

    def test_unreadable_queue_is_optional(self):
        with mock.patch.object(scanner.os, "scandir", side_effect=PermissionError):
            self.assertEqual([], scanner.collect_scan_dirs("", ""))


if __name__ == "__main__":
    unittest.main()
