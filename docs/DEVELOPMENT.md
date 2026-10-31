# Developer guide

This is for anyone maintaining Fix Photo Dates. Start with the
[README](../README.md). It's the single source of truth for what the app does:
the tabs, every file name it recognises, the rules for each file and the
limitations users see. This guide only covers how that's built, and links back
to the README rather than repeating it.

## Who it's for

The problem is in the README's opening paragraph. The intended user is not
technical and has nothing installed. That drives most
of the design:

- **One `.exe` with everything bundled.** No Python and no installer.
- **A simple window.** Three tabs, each doing one job: **Fix dates** (dates
  only), **Organise** (names and month folders only) and **Renumber** (close
  gaps after deleting). Each reads top to bottom: a short explanation,
  **1. Choose folder**, the preview list, then the **2.** button under the
  list. Messages are in plain English.
- **Nothing changes until step 2 is clicked.** Choosing a folder and changing
  options only previews the changes.
- **Updates itself.** The app offers new versions itself, so the user never
  has to visit GitHub.

## Files

| File | Purpose |
| ---- | ------- |
| [datefromname.py](../datefromname.py) | All the date logic: parsing names, reading and writing dates, deciding what to do. It has no GUI code and also works as a command-line tool. |
| [app.py](../app.py) | The tkinter window, the entry point for the `.exe`. It's a thin layer over `datefromname`. `Tab` holds the shared two-step layout (choose, preview, go, done). `FixTab`, `OrganiseTab` and `RenumberTab` fill in `scan()` and `show_plan()`, and `OrganiseTab` adds `build_options()`. Another job would be another `Tab` subclass. The preview list is a `ColourTable` (a read-only `tk.Text` lined up with tab stops), because `ttk.Treeview` can only colour whole rows. In the "New name" column, the month folder is green (`FOLDER_COLOUR`) and the date prefix is blue (`PREFIX_COLOUR`), matching the Organise choices. |
| [updater.py](../updater.py) | Checks GitHub Releases and swaps in the new `.exe`. |
| [_version.py](../_version.py) | `VERSION = "dev"` in the repo. The release workflow overwrites it with the tag. |
| [tests/](../tests/) | The test suite. See [Tests](#tests). |
| [.github/workflows/test.yml](../.github/workflows/test.yml) | Runs the tests on every push to `main` and every pull request. |
| [.github/workflows/release.yml](../.github/workflows/release.yml) | On a `v*` tag, it tests, builds and publishes the release. |
| [.githooks/commit-msg](../.githooks/commit-msg) | Rejects commit messages that aren't Conventional Commits. See [CONTRIBUTING.md](../CONTRIBUTING.md). |
| `requirements.txt` / `requirements-dev.txt` | `piexif` is the only thing bundled into the exe. Pillow, pillow-heif (to make test images) and a pinned PyInstaller are for development and building. |
| [CHANGELOG.md](../CHANGELOG.md) | What changed in each release. Update it before tagging. |
| [LICENSE](../LICENSE) | MIT. |

## How a file is processed

Sections 1 to 3 are the **Fix dates** tab (`FixTab`), section 4 is
**Organise** and **Renumber**, and section 5 is the log. Every job works the
same way: a `plan_*()` function builds a list of `Plan`s (what would happen to
each file) without touching anything, the window shows them, and
`apply_plans()` makes the changes.

`plan_folder()` makes two passes over the folder.

### 1. Read the name and the date inside the file

`parse_name()` tries the regexes in `PATTERNS` in order and the first valid
date wins, so the most specific patterns come first. Every match of a pattern
is tried, so an invalid date earlier in the name doesn't hide a valid one
later. The patterns use named groups: `y m d` for the date, `H M S` for the
time, `ampm` for a 12-hour clock, `seq` for the WhatsApp order number, and
`epoch` for Unix seconds (Facebook `FB_IMG_`, iPhone `RPReplay_Final`, or
names that are just a timestamp; a 13-digit millisecond value is cut to
seconds). The README table lists every layout we know of, with examples, and
`ParseNameTests` has a case for each.

Each pattern has a *kind*:

| Kind | Example | Meaning |
| ---- | ------- | ------- |
| `DATE_ONLY` | `IMG-20260822-WA0004.jpeg` | The day is known but not the time. WhatsApp names also carry an order number (`WA0004`), kept as `seq`. |
| `UTC_TIME` | `PXL_20260822_092200562.MP.jpg`, `FB_IMG_1787398496123.jpg` | Google Pixel names and Unix timestamps are **UTC**, not local time. |
| `LOCAL_TIME` | `IMG_20260822_123456.jpg`, `Screenshot_20260822-123456.png` | The date and time are local. |

Years outside 1990 to next year, and impossible dates or times, are rejected,
so random digit runs don't count as dates.

iPhones (`IMG_1234.HEIC/.JPG/.MOV`) and dedicated cameras (`DSC_1234.JPG`, GoPro `GX010123.MP4`)
have **no date in the name**. `parse_name()` returns `None` for them, and they
are only processed if a date can be read from inside the file. In that case the
date inside is kept and only the Windows dates are lined up with it. A file with
neither goes to the skipped list.

`read_embedded_date()` reads the date already stored inside the file:

- **JPEG:** EXIF `DateTimeOriginal`, falling back to `DateTimeDigitized`, read
  via piexif. These are local time with no zone.
- **MP4/MOV/M4V/3GP:** the `mvhd` creation time, in UTC seconds since 1904. It
  is converted to local time. A value of 0 counts as "no date".
- **HEIC/HEIF (iPhone):** the EXIF date is **read only**. HEIC uses the same
  box layout as MP4. `read_heic_date()` finds the item of type `Exif` in
  `meta/iinf`, looks up its bytes in `meta/iloc`, skips the 4-byte offset
  prefix and hands the TIFF data to piexif. We never write HEIC, so if a HEIC
  date is wrong only the Windows dates change. Tested with real HEIC files made
  by `pillow-heif` (a dev-only dependency; the test is skipped without it).
- **Anything else** (PNG, RAW and so on) counts as having no date inside. Only
  the Windows file dates are changed.

### 2. Decide (`_decide`)

The rules are listed under "For each file" in the README's
[Fix dates](../README.md#fix-dates) section. `_decide()` checks them in that
order:

- **Agrees** (`_agrees()`): within `TIME_ZONE_SLACK` (14 hours) for timed
  names, to allow for any time zone, or the same day for date-only names.
- **Older**: more than a day before the name's date. This is treated as an
  edited copy of an older photo, so the date inside is trusted.
- **Later**: usually the download or re-encode time, so it's overwritten.

When writing a date from a `DATE_ONLY` name:

- If the file's **modified date is already on the right day**, use that
  timestamp, because the real time survived (e.g. some WhatsApp videos).
- Otherwise use **12:00:00 plus `seq` seconds**. The order number works like
  ticket numbers at a deli counter: it doesn't say *when* each photo arrived,
  only the order, and adding it as seconds keeps photos sorting in that order.

When writing a date from a `UTC_TIME` (Pixel) name, the time is converted to
the time zone **the phone was in**, which may not be the PC's. `_pixel_offsets()`
looks at Pixel photos in the same folder that still have EXIF and measures the
gap between the EXIF time and the file name's UTC time, rounded to 15 minutes.
The nearest such photo's offset is used. If there aren't any, the PC's time
zone is used.

Finally, the Windows **created** and **modified** dates are set to the chosen
date if either is more than 2 seconds out. This happens even when the date
inside the file was already right, so sorting by date works everywhere.

### 3. Write (`apply_plan`)

- **JPEG:** `piexif.insert()` replaces only the EXIF block, so the picture data
  is not re-encoded. We checked that piexif keeps everything after the image
  data, so the video inside a Pixel "motion photo" (`.MP.jpg`) survives. There
  is a test for this.
- **MP4:** the file is opened in place and the creation and modification time
  fields in `mvhd`, every `tkhd` and every `mdhd` are overwritten. These are
  fixed-width fields, so nothing moves and the rest of the file is never
  touched. 64-bit (version 1) boxes are handled.
- **Windows file dates:** `os.utime` sets the modified date. The created date
  needs the Win32 `SetFileTime` call through ctypes, because Python can't set it
  directly.

If writing the date inside a file fails, the Windows dates are still set and
the error is shown in the window and recorded in the log. One bad file doesn't
stop the rest.

### 4. Organise: rename and sort into month folders

This is the **Organise** tab (`OrganiseTab`). It never changes dates.
`plan_organise()` runs `plan_folder()` to get each file's date (`plan.target`,
the corrected date even though it isn't written), adds the undated files as
plain `Plan`s, and clears `write_embedded`/`set_file_times`. Then
`plan_new_paths(plans, root, prefix, folders)` sets `plan.new_path`. The window
calls it again whenever a choice changes, so the preview is always up to date.

- **`prefix`**: `LEAVE`, `ADD` or `REMOVE`.
  - `ADD` gives `YYYY_MM_DD_####_<original name>`. Files are grouped by
    destination folder and month and sorted by date, then name, and `####`
    counts from `0000`. Any existing prefix matching `PREFIX` is stripped
    first, so running twice is a no-op and adding photos renumbers the month.
    Undated files keep their name.
  - `REMOVE` strips `PREFIX`.
  - `parse_name()` also strips the prefix, so prefixed WhatsApp and Pixel
    names still parse.
- **`folders`**: `LEAVE`, `INTO` or `OUT`.
  - `INTO` moves every dated file into `<root>/YYYY_MM/`, wherever it was.
    Numbering is per destination folder, so with both it's "oldest of the
    month in that folder is 0000". If `root` is itself a month folder, the
    month folders go beside it (`months_in` is its parent), so choosing
    `2026_08` never makes `2026_08/2026_08`.
  - `OUT` moves files whose folder matches `MONTH_FOLDER` (`^\d{4}_\d{2}$`)
    up one level, dated or not. Their original subfolders aren't recorded, so
    `OUT` can't restore them.
- **Name clashes** within a destination get ` (2)`, ` (3)` and so on. The
  `used` names set is shared per folder. Plain (unnumbered) groups are
  assigned first, with files already in the folder ahead of newcomers, so a
  file that isn't moving keeps its name. A clash with a file that isn't part
  of the plan is caught at apply time. That file is put back where it was and
  the clash is reported.

The command line has the same choices as `--rename`, `--remove-prefix`,
`--month-folders` and `--out-of-month-folders`.

`apply_plans()` fixes the dates first, then does all the renames in two steps:
first to `~renaming<n>~<name>` in the original folder, then to the final path.
Renumbering can make one file's new name another file's current name, like
two parked cars swapping spaces, so every file moves aside before any takes
its new spot. If the final step fails, the file is renamed back. Afterwards,
`_remove_emptied_folders()` uses `os.rmdir` (which only removes empty folders)
on each folder a file left, and its parents up to the chosen folder.

If the app is killed between the two steps, files can be left with a
`~renaming` name. Running the app again won't repair those.

**Renumber** is a separate tab for closing gaps after the user deletes
photos. (Organise with "Add it" also renumbers, but it reads every file's date
and would add prefixes to unnumbered files too.) `plan_renumber()` looks only
at files whose name matches `PREFIX`, groups them by folder and the prefix's year and month, sorts by
(prefix day, old number, name) and numbers them from `0000`. It reads nothing
inside the files, so the order is exactly the existing order and it's fast. It
returns plain `Plan`s with only `new_path` set, so `apply_plans()` does the
renaming with the same two-step swap (`RenumberTab`).

Because the prefix itself is a date, `parse_name()` falls back to it (as
`DATE_ONLY`, with the number as `seq`) when the rest of the name has no date,
e.g. `2026_09_02_0001_DSC_1234.JPG`. Without that, running **Fix dates** again
would skip those files.

### 5. Log

A CSV log of every file is **optional and off by default**, so logs don't pile
up on the user's PC. It's saved only when the "Save a list of the changes" tick
box at the bottom of the window is ticked. It applies to every tab. It goes in
a `FixPhotoDates logs` folder next to the `.exe` (or next to `app.py` when run
from source), named
`FixPhotoDates log <date time>.csv`. The command-line tool never writes a log.

## Self-update

The repo is public, so the app can ask the GitHub API for the latest release
without logging in:
`https://api.github.com/repos/TomZandt/DateFromName/releases/latest`.

1. **On start-up** (only in the built `.exe`; `can_update()` is false when run
   from source or when the version is `dev`), a background thread compares the
   release tag with `VERSION` as number tuples (`v1.10.0` > `v1.9.0`). If it's
   offline or GitHub doesn't answer, nothing happens.
2. **If the release is newer,** a yellow bar appears with **Update now**.
3. **Update now** downloads `FixPhotoDates.exe` to `FixPhotoDates.exe.download`
   next to the running exe. Then it swaps the files in, starts the new exe and
   closes.

The swap gets around a Windows rule: **a running exe can't be overwritten or
deleted, but it can be renamed.** It's like moving into a new house while still
living in the old one: you can't knock the old house down while you're inside,
but you can change its address and move the new one into the old address. So:

```
FixPhotoDates.exe          -> FixPhotoDates.old.exe   (rename the running one)
FixPhotoDates.exe.download -> FixPhotoDates.exe       (new one takes its place)
```

The next launch deletes `FixPhotoDates.old.exe` (`remove_old_version()`). If
the second rename fails, the old exe is put back. If anything goes wrong, the
app opens the releases page in the browser instead.

Downloads made by the app don't get Windows' "downloaded from the internet"
mark, so updates don't trigger the SmartScreen warning. Only the first,
browser-downloaded copy does.

**Don't rename these without care**, because existing copies depend on them:

- **The repo name and `REPO` in `updater.py`:** the app asks this repo for
  updates.
- **The asset name `FixPhotoDates.exe`:** the app looks for this exact name.
- **The tag format `vX.Y.Z`:** numbers only. A tag like `v1.1-beta` can't be
  compared and is ignored.

If the repo ever has to move, release one last version from the *old* repo
with `REPO` pointing at the new one.

## Releasing

Version numbers follow Semantic Versioning. How to pick the next number, and
how it follows from the commit types, is in
[CONTRIBUTING.md](../CONTRIBUTING.md#versions-semantic-versioning).

### Before a release

1. Work out the next version from the commits since the last tag:
   `git log --oneline $(git describe --tags --abbrev=0)..HEAD`
2. Make sure `main` is clean (`git status`) and the tests pass.
3. Build the exe locally (see [Working locally](#working-locally)), open it
   and click through each tab on a copy of some test photos. The tests don't
   cover the built exe.
4. Check the docs match what's changed: the README for anything users see,
   this guide for how it works, CONTRIBUTING for process.
5. In [CHANGELOG.md](../CHANGELOG.md), rename "Unreleased" to the new
   version and date. Commit with `docs(release): vX.Y.Z`.
6. Tag and push:

```
git tag vX.Y.Z
git push origin main vX.Y.Z
```

The workflow runs on `windows-latest` (about 1 minute):

1. Installs the dependencies and runs the tests. If they fail, nothing is
   released.
2. Writes the tag into `_version.py`.
3. Runs `pyinstaller --onefile --windowed --name FixPhotoDates app.py`.
4. Runs `gh release create` with the exe attached and auto-generated notes.

Each new tag must be numerically higher than the last, or installed copies
won't offer it (see [Self-update](#self-update)).

Give users the download link in the README. It always points at the newest
release.

### After a release

1. **Check it published:** `gh run list --workflow Release --limit 1` shows
   success, and `gh release view vX.Y.Z` lists `FixPhotoDates.exe`.
2. **Check what users get:** download from the README link and open it. The
   title should say `Fix Photo Dates (vX.Y.Z)`.
3. **Check updating:** open the previous version's exe (from its release
   page). The yellow bar should offer the new version, and **Update now**
   should restart it as the new version with no warning box.
4. **Tidy up locally:** delete `build/`, `dist/` and `*.spec` if you built
   locally (they're git-ignored, but old builds are easy to mix up), and any
   copies of test photos.
5. **Changelog:** the next change that users will notice starts a new
   `## Unreleased` section at the top of CHANGELOG.md.

If something's wrong with a release, don't move or delete the tag. Fix it and
release a new PATCH version (see
[CONTRIBUTING.md](../CONTRIBUTING.md#versions-semantic-versioning)).

### After merging a branch

Branches and pull requests are described in
[CONTRIBUTING.md](../CONTRIBUTING.md#branches-and-pull-requests). After one is
merged:

1. **The branch is deleted on GitHub automatically.** The repo has
   **Settings → General → Automatically delete head branches** turned on.
2. **Tidy up locally:**

   ```
   git switch main
   git pull
   git branch -d <branch>
   git fetch --prune
   ```

3. **Check the Test workflow** passed on `main` after the merge
   (`gh run list --workflow Test --limit 1`).
4. **Decide whether it needs a release.** Use the rules in
   [CONTRIBUTING.md](../CONTRIBUTING.md#picking-the-next-version):
   docs/test/CI-only changes don't.

## Working locally

```
pip install -r requirements.txt -r requirements-dev.txt
git config core.hooksPath .githooks              # check commit messages
python -m unittest discover -s tests -v
python app.py                                  # the window
python datefromname.py "D:\Photos"             # preview on the command line
python datefromname.py "D:\Photos" --apply     # fix on the command line
python datefromname.py "D:\Photos" --rename --month-folders --apply
python datefromname.py "D:\Photos" --remove-prefix --out-of-month-folders --apply
```

To build the exe locally:

```
pyinstaller --onefile --windowed --name FixPhotoDates app.py
```

The output goes to `dist/`. `build/`, `dist/` and `*.spec` are git-ignored. A
local build reports its version as `dev` and never updates itself.

Always try changes on a **copy** of a photo folder. The app changes files in
place, and date fixes can't be undone.

To try the window without your own photos, make test files with the helpers in
the tests (`make_jpeg`, `make_mp4`), e.g. a few `IMG-YYYYMMDD-WAnnnn.jpeg`
files with no EXIF and a `PXL_` file with EXIF.

## Tests

```
python -m unittest discover -s tests -v
```

They run in a couple of seconds, on every push (`test.yml`) and before every
release. Every test works on generated files in a temporary folder and never
touches real photos or the network.

| File | Covers |
| ---- | ------ |
| `test_datefromname.py` | Reading names (every format in the README table, and names that shouldn't count), reading and writing dates in JPEG, MP4 (32- and 64-bit headers) and HEIC, the Fix dates rules, Organise (add, remove, into, out, running twice, choosing a month folder, duplicate names), Renumber, and what happens when things go wrong: clashes, failed renames rolling back, damaged and read-only files. Also the log and the command line. `make_jpeg()` and `make_mp4()` build test files. |
| `test_updater.py` | Version comparison, when an update is offered, and the exe swap and rollback, with GitHub and the exe faked. |
| `test_app.py` | Smoke tests for the window: each tab is driven like a user would (choose folder, check the message and preview, click the button) with the folder picker faked and the window hidden. Also the log tick box, problems being listed and the update bar. Skipped if there's no display. |

Not covered: real files from real phones (all test files are generated), and
the built `.exe` itself. Before a release, open the sample folder in the
built exe once (see [Working locally](#working-locally)).

## Common changes

**Adding a file name format.** First check whether the general
date-and-time pattern already handles it. It accepts `-`, `_`, `.` or nothing
between the date parts, and most separators between the date and the time.
Add the name to `ParseNameTests.test_patterns` and run the tests. If it fails,
add a `(regex, kind)` entry to `PATTERNS` with named groups, above any broader
pattern it would otherwise lose to. Then mention it in the README table.

**Supporting another file type's internal date** (e.g. PNG or RAW). Add a
reader and a writer, branch on the extension in `read_embedded_date()` and
`apply_plan()`, and add the extension to `write_embedded` in `_decide()`. Until
then these types only get their Windows dates fixed.

**Changing what "agrees" means.** That's `_agrees()` and `TIME_ZONE_SLACK`.
Loosening them means fewer files get changed. Tightening them risks
overwriting correct dates that were recorded in another time zone.

## Known limitations

Limitations users notice are in the README's
[Good to know](../README.md#good-to-know) section. These are the
developer-facing ones:

- **The exe is unsigned,** so the first run shows SmartScreen's "Windows
  protected your PC" (the README tells users how to get past it). A
  code-signing certificate would remove this.
- **If the app is closed mid-rename**, files can be left named `~renaming…`.
  Nothing repairs them automatically.
- **The pattern for names that are just a timestamp** (`^\d{10}`) would also
  treat any other 10- or 13-digit name as a date, as long as it falls in a
  plausible year.
- **HEIC, PNG and RAW dates are never written,** only read (HEIC) or ignored.
  See "Supporting another file type's internal date" above.
- **Updating from v1.0.0 or v1.1.0** shows a harmless "Failed to remove
  temporary directory" warning once, because those versions start the new exe
  the old way. Fixed from v1.1.1 on.
- **The workflow uses `actions/checkout@v4` and `actions/setup-python@v5`.**
  GitHub warns these use the deprecated Node 20. It still works. Bump them to
  their Node 24 versions when convenient.
