"""Self-update from the GitHub releases page.

The release workflow stamps the version into _version.py and attaches
FixPhotoDates.exe to the release. On start-up the app asks GitHub for the
latest release; if it is newer, "Update now" downloads the new exe, swaps it
in place of the running one and restarts. Windows will not let a running exe
be overwritten, but it can be renamed, so the old one is moved aside and
deleted the next time the app starts.
"""

import json
import os
import subprocess
import sys
import urllib.request

from _version import VERSION

REPO = "TomZandt/DateFromName"
ASSET_NAME = "FixPhotoDates.exe"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def _version_tuple(tag):
    try:
        return tuple(int(part) for part in tag.lstrip("vV").split("."))
    except ValueError:
        return ()


def can_update():
    """Only the built exe updates itself; running from source never does."""
    return getattr(sys, "frozen", False) and bool(_version_tuple(VERSION))


def _old_exe_path():
    return os.path.splitext(sys.executable)[0] + ".old.exe"


def remove_old_version():
    try:
        os.remove(_old_exe_path())
    except OSError:
        pass


def check_for_update():
    """Return (tag, download url) if a newer release exists, else None."""
    request = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            release = json.load(response)
    except Exception:
        return None  # offline or GitHub unreachable: just carry on
    tag = release.get("tag_name", "")
    if _version_tuple(tag) <= _version_tuple(VERSION):
        return None
    for asset in release.get("assets", []):
        if asset.get("name") == ASSET_NAME:
            return tag, asset["browser_download_url"]
    return None


def install_update(url, progress=None):
    """Download the new exe, put it in place of this one and restart it."""
    exe = sys.executable
    new_exe = exe + ".download"
    with urllib.request.urlopen(url, timeout=60) as response, open(new_exe, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(256 * 1024):
            out.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done, total)
    remove_old_version()
    os.replace(exe, _old_exe_path())
    try:
        os.replace(new_exe, exe)
    except OSError:
        os.replace(_old_exe_path(), exe)  # put the working version back
        raise
    # Without this the new exe reuses our unpacked temp folder, so we can't
    # delete it on exit and Windows shows "Failed to remove temporary directory".
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen([exe], env=env, close_fds=True)
