"""Smoke tests for the window: each tab is driven like a user would."""

import os
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app  # noqa: E402
import datefromname as core  # noqa: E402
from test_datefromname import make_jpeg  # noqa: E402


class AppTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        mock.patch.object(app.filedialog, "askdirectory", side_effect=lambda **k: self.dir).start()
        mock.patch.object(app.updater, "can_update", return_value=False).start()
        self.app = app.App(self.root)

    def tearDown(self):
        mock.patch.stopall()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def files(self):
        return sorted(os.path.relpath(os.path.join(root, f), self.dir).replace("\\", "/")
                      for root, _, names in os.walk(self.dir) for f in names)

    def wait_for(self, condition, timeout=10):
        """Run the window until condition() is true (background work reports back through it)."""
        def check():
            if condition():
                self.root.quit()
            else:
                self.root.after(20, check)
        self.root.after(0, check)
        self.root.after(timeout * 1000, self.root.quit)
        self.root.mainloop()
        self.assertTrue(condition(), "timed out")

    def scan(self, tab):
        tab.choose_folder()
        self.wait_for(lambda: tab.plans is not None)

    def go(self, tab):
        tab.go()
        self.wait_for(lambda: tab.message.cget("text").startswith("Done"))
        return tab.message.cget("text")

    def test_fix_dates_tab(self):
        make_jpeg(self.path("IMG-20260822-WA0002.jpeg"))
        tab = self.app.fix_tab
        self.scan(tab)
        self.assertIn("1 will have their date fixed", tab.message.cget("text"))
        self.assertEqual(tab.go_button.cget("text"), "2.  Fix 1 dates")
        self.assertIn("Done!  1 photos", self.go(tab))
        self.assertIsNotNone(core.read_jpeg_date(self.path("IMG-20260822-WA0002.jpeg")))
        self.assertEqual(str(tab.go_button.cget("state")), "disabled")

    def test_organise_tab(self):
        make_jpeg(self.path("IMG-20260822-WA0002.jpeg"))
        tab = self.app.organise_tab
        self.scan(tab)
        self.assertIn("Choose what you'd like to do", tab.message.cget("text"))
        self.assertEqual(str(tab.go_button.cget("state")), "disabled")
        tab.prefix.set(core.ADD)
        tab.folders.set(core.INTO)
        tab.show_plan()
        self.assertEqual(tab.go_button.cget("text"), "2.  Organise 1 files")
        preview = tab.table.text.get("1.0", "end")
        self.assertIn("2026_08\\2026_08_22_0000_IMG-20260822-WA0002.jpeg", preview)
        self.assertTrue(tab.table.text.tag_ranges("prefix"))
        self.assertTrue(tab.table.text.tag_ranges("folder"))
        self.go(tab)
        self.assertEqual(self.files(), ["2026_08/2026_08_22_0000_IMG-20260822-WA0002.jpeg"])
        self.assertIsNone(core.read_jpeg_date(self.path("2026_08/2026_08_22_0000_IMG-20260822-WA0002.jpeg")))

    def test_renumber_tab(self):
        make_jpeg(self.path("2026_08_22_0001_a.jpg"))
        make_jpeg(self.path("2026_08_22_0005_b.jpg"))
        tab = self.app.renumber_tab
        self.scan(tab)
        self.assertIn("2 will get a new number", tab.message.cget("text"))
        self.go(tab)
        self.assertEqual(self.files(), ["2026_08_22_0000_a.jpg", "2026_08_22_0001_b.jpg"])
        self.scan(tab)
        self.assertIn("already in order", tab.message.cget("text"))

    def test_empty_folder(self):
        for tab in (self.app.fix_tab, self.app.organise_tab):
            self.scan(tab)
            self.assertIn("no photos or videos", tab.message.cget("text"))
        self.scan(self.app.renumber_tab)
        self.assertIn("None of the photos", self.app.renumber_tab.message.cget("text"))

    def test_log_is_saved_only_when_ticked(self):
        logs = os.path.join(self.dir, "logs")
        mock.patch.object(app, "log_folder", return_value=logs).start()
        make_jpeg(self.path("IMG-20260822-WA0002.jpeg"))
        tab = self.app.fix_tab
        self.scan(tab)
        self.go(tab)
        self.assertFalse(os.path.exists(logs))

        make_jpeg(self.path("IMG-20260823-WA0002.jpeg"))
        self.app.save_log.set(True)
        self.scan(tab)
        self.assertIn("A record of the changes was saved", self.go(tab))
        self.assertEqual(len(os.listdir(logs)), 1)

    def test_problems_are_listed(self):
        with open(self.path("IMG-20260822-WA0002.jpg"), "wb") as f:
            f.write(b"not really a jpeg")
        tab = self.app.fix_tab
        self.scan(tab)
        self.assertIn("1 had a problem", self.go(tab))
        self.assertIn("Could not write date inside file", tab.table.text.get("1.0", "end"))

    def test_update_bar_appears_when_a_new_version_is_out(self):
        self.assertFalse(self.app.update_bar.winfo_ismapped())
        with mock.patch.object(app.updater, "check_for_update", return_value=("v9.9.9", "https://x")):
            self.app._check_for_update()
        self.root.deiconify()
        self.wait_for(lambda: self.app.update_bar.winfo_ismapped())
        self.assertIn("v9.9.9", self.app.update_text.cget("text"))


if __name__ == "__main__":
    unittest.main()
