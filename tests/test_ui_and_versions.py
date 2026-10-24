import ctypes
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cp77_crash_scanner as scanner


class FileTreeTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.open_path = mock.Mock()
        self.trees = [ttk.Treeview(self.root, columns=("name", "size")) for _ in range(5)]
        self.rows = [scanner.FileTreeRows(t, self.open_path, sortable=True) for t in self.trees]

    def click(self, tree, rows, iid, region="cell"):
        with mock.patch.object(tree, "identify_region", return_value=region), \
                mock.patch.object(tree, "identify_row", return_value=iid):
            rows.on_double_click(SimpleNamespace(x=10, y=30))

    def test_identical_row_ids_in_five_tabs_open_their_own_files(self):
        for index, (tree, rows) in enumerate(zip(self.trees, self.rows)):
            tree.insert("", "end", iid="I001", values=("file", "1 KB"))
            rows.add("I001", f"tab-{index}.log")
        for index, (tree, rows) in enumerate(zip(self.trees, self.rows)):
            self.click(tree, rows, "I001")
            self.open_path.assert_called_with(f"tab-{index}.log")
        self.assertEqual(5, self.open_path.call_count)

    def test_heading_blank_area_and_group_do_not_open_focused_file(self):
        tree, rows = self.trees[0], self.rows[0]
        tree.insert("", "end", iid="file")
        tree.insert("", "end", iid="group")
        tree.focus("file")
        rows.add("file", "error.log")
        for region, iid in [("heading", "file"), ("nothing", ""), ("tree", "group")]:
            self.click(tree, rows, iid, region)
        self.open_path.assert_not_called()

    def test_sort_headers_toggle_and_keep_file_links(self):
        tree, rows = self.trees[0], self.rows[0]
        data = [("a", "z.log", "900 KB", 900 * 1024),
                ("b", "Alpha.log", "2 MB", 2 * 1024**2),
                ("c", "beta.log", "?", None)]
        for iid, name, size, raw_size in data:
            tree.insert("", "end", iid=iid, values=(name, size))
            rows.add(iid, name, raw_size)
        # Invoke actual Tk heading callbacks.
        tree.tk.call(tree.heading("size", "command"))
        self.assertEqual(("a", "b", "c"), tree.get_children())
        tree.tk.call(tree.heading("size", "command"))
        self.assertEqual(("b", "a", "c"), tree.get_children())
        tree.tk.call(tree.heading("name", "command"))
        self.assertEqual(("b", "c", "a"), tree.get_children())
        tree.tk.call(tree.heading("name", "command"))
        self.assertEqual(("a", "c", "b"), tree.get_children())
        self.click(tree, rows, "b")
        self.open_path.assert_called_once_with("Alpha.log")

    def test_refresh_clears_old_paths_and_reapplies_sort(self):
        tree, rows = self.trees[0], self.rows[0]
        tree.insert("", "end", iid="old", values=("old.log", "1 B"))
        rows.add("old", "old.log", 1)
        rows.sort("size")
        rows.clear()
        tree.delete(*tree.get_children())
        for iid, size in [("big", 2048), ("small", 100)]:
            tree.insert("", "end", iid=iid, values=(iid, str(size)))
            rows.add(iid, iid + ".log", size)
        rows.apply_sort()
        self.assertEqual(("small", "big"), tree.get_children())
        self.click(tree, rows, "old")
        self.open_path.assert_not_called()


class VersionDetectionTests(unittest.TestCase):
    def scan(self, game_dir):
        with mock.patch.object(scanner, "detect_vortex_dir", return_value=None), \
                mock.patch.object(scanner, "load_config", return_value={}):
            return scanner.scan("", str(game_dir))

    def test_file_version_reads_version_fields_not_signature(self):
        # The previous reader interpreted FEEF04BD as 65263.1213.1.
        data = ctypes.create_string_buffer(struct.pack(
            "<13I", 0xFEEF04BD, 0x10000, 5, 31 << 16, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        api = mock.Mock()
        api.GetFileVersionInfoSizeW.return_value = len(data)
        api.GetFileVersionInfoW.return_value = 1

        def query(buffer, key, pointer, length):
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(data)
            ctypes.cast(length, ctypes.POINTER(ctypes.c_uint))[0] = 52
            return 1

        api.VerQueryValueW.side_effect = query
        with mock.patch.object(ctypes, "windll", SimpleNamespace(version=api), create=True):
            self.assertEqual("0.5.31", scanner._win_file_version("scc.exe"))
            data[0] = b"\x00"
            self.assertIsNone(scanner._win_file_version("invalid.exe"))

    def test_frameworks_detected_without_crash_or_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for candidates in scanner.FRAMEWORK_BINARIES.values():
                path = Path(tmp) / candidates[0]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with mock.patch.object(scanner, "_win_file_version", return_value="1.2.3"):
                result = self.scan(tmp)
            self.assertEqual(set(scanner.CORE_FRAMEWORKS), set(result.versions))
            self.assertEqual(0, result.scanned_files)

    def test_redmod_compiler_is_not_redscript(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tools/redmod/bin/scc.exe"
            path.parent.mkdir(parents=True)
            path.touch()
            with mock.patch.object(scanner, "_win_file_version", return_value="9.9.9"):
                self.assertNotIn("redscript", self.scan(tmp).versions)

    def test_startup_versions_survive_long_logs_without_importing_old_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "red4ext/logs/red4ext.log"
            path.parent.mkdir(parents=True)
            path.write_text("RED4ext (v1.30.0) is initializing\n"
                            "[error] old error outside tail\n" + "[info] normal\n" * 100,
                            encoding="utf-8")
            with mock.patch.object(scanner, "MAX_READ_BYTES", 128), \
                    mock.patch.object(scanner, "read_tail", side_effect=lambda p: scanner.read_capped(p, 128)[0]):
                result = self.scan(tmp)
            self.assertEqual("1.30.0", result.versions["RED4ext"])
            self.assertEqual([], result.findings)

    def test_plugin_log_is_scanned_and_log_version_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "red4ext/plugins/ArchiveXL/ArchiveXL.log"
            path.parent.mkdir(parents=True)
            path.write_text("ArchiveXL (version: 1.26.8) has been loaded\n", encoding="utf-8")
            path.with_suffix(".dll").touch()
            with mock.patch.object(scanner, "_win_file_version", return_value="1.0.0"):
                result = self.scan(tmp)
            self.assertEqual("1.26.8", result.versions["ArchiveXL"])
            self.assertEqual(1, result.scanned_files)


if __name__ == "__main__":
    unittest.main()
