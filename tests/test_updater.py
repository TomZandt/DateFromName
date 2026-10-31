import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import updater  # noqa: E402


class FakeResponse(io.BytesIO):
    """Stands in for what urllib.request.urlopen returns."""

    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


def release(tag, asset=updater.ASSET_NAME):
    assets = [{"name": asset, "browser_download_url": f"https://example.invalid/{tag}/{asset}"}]
    return FakeResponse(json.dumps({"tag_name": tag, "assets": assets}).encode())


class VersionTests(unittest.TestCase):
    def test_versions_compare_as_numbers(self):
        self.assertGreater(updater._version_tuple("v1.10.0"), updater._version_tuple("v1.9.0"))
        self.assertEqual(updater._version_tuple("V2.0"), (2, 0))

    def test_non_numeric_versions_are_ignored(self):
        for tag in ("dev", "v1.1-beta", ""):
            self.assertEqual(updater._version_tuple(tag), ())

    def test_only_built_numbered_exe_updates(self):
        with mock.patch.object(updater, "VERSION", "v1.0.0"):
            self.assertFalse(updater.can_update())  # running from source
            with mock.patch.object(sys, "frozen", True, create=True):
                self.assertTrue(updater.can_update())
        with mock.patch.object(updater, "VERSION", "dev"), \
                mock.patch.object(sys, "frozen", True, create=True):
            self.assertFalse(updater.can_update())


class CheckTests(unittest.TestCase):
    def check(self, response, current="v1.2.0"):
        with mock.patch.object(updater, "VERSION", current), \
                mock.patch("urllib.request.urlopen", **response):
            return updater.check_for_update()

    def test_newer_release_is_offered(self):
        tag, url = self.check({"return_value": release("v1.3.0")})
        self.assertEqual(tag, "v1.3.0")
        self.assertTrue(url.endswith("/v1.3.0/FixPhotoDates.exe"))

    def test_same_or_older_release_is_not_offered(self):
        self.assertIsNone(self.check({"return_value": release("v1.2.0")}))
        self.assertIsNone(self.check({"return_value": release("v1.1.9")}))

    def test_release_without_the_exe_is_not_offered(self):
        self.assertIsNone(self.check({"return_value": release("v1.3.0", asset="Other.zip")}))

    def test_offline_is_quiet(self):
        self.assertIsNone(self.check({"side_effect": OSError("no internet")}))


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.exe = os.path.join(self.tmp.name, "FixPhotoDates.exe")
        with open(self.exe, "wb") as f:
            f.write(b"old version")
        self.patches = [
            mock.patch.object(sys, "executable", self.exe),
            mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"new version")),
        ]
        for p in self.patches:
            p.start()
        self.popen = mock.patch("subprocess.Popen").start()
        self.patches.append(self.popen)

    def tearDown(self):
        mock.patch.stopall()
        self.tmp.cleanup()

    def read(self, path):
        with open(path, "rb") as f:
            return f.read()

    def test_new_exe_replaces_old_and_restarts(self):
        progress = []
        updater.install_update("https://example.invalid/x", progress=lambda d, t: progress.append((d, t)))
        self.assertEqual(self.read(self.exe), b"new version")
        self.assertEqual(self.read(self.exe[:-4] + ".old.exe"), b"old version")
        self.assertEqual(progress[-1], (11, 11))
        args, kwargs = self.popen.call_args
        self.assertEqual(args[0], [self.exe])
        # Without this the restarted exe shows "Failed to remove temporary directory".
        self.assertEqual(kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_old_exe_is_put_back_if_the_swap_fails(self):
        real_replace = os.replace

        def replace(src, dst):
            if src.endswith(".download"):
                raise PermissionError("locked")
            return real_replace(src, dst)

        with mock.patch("os.replace", side_effect=replace):
            with self.assertRaises(PermissionError):
                updater.install_update("https://example.invalid/x")
        self.assertEqual(self.read(self.exe), b"old version")
        self.popen.assert_not_called()

    def test_old_version_is_cleaned_up_next_time(self):
        old = self.exe[:-4] + ".old.exe"
        with open(old, "wb") as f:
            f.write(b"old version")
        updater.remove_old_version()
        self.assertFalse(os.path.exists(old))
        updater.remove_old_version()  # nothing there: no error


if __name__ == "__main__":
    unittest.main()
