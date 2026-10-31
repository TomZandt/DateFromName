# Developer guide

This is for anyone maintaining Fix Photo Dates. The [README](../README.md) is the
user-facing overview.

## The problem it solves

When photos are downloaded from Google Photos to Windows, some lose their
"Date taken", especially WhatsApp ones, which have it stripped when sent. Windows
then shows the download date, so a whole summer's photos all appear as
"31/10/2026 12:21" and sort in the wrong order. The file names still hold the
real date (`IMG-20260822-WA0004.jpeg`), so the app copies that date back into
the file.

The intended user is not technical and has nothing installed. That drives most
of the design:

- **One `.exe` with everything bundled.** No Python and no installer.
- **A simple window.** Two big buttons, plain-English messages and no settings.
- **Nothing changes until "Fix dates" is clicked.** Choosing a folder only
  previews the changes.
- **Updates itself.** The app offers new versions itself, so the user never
  has to visit GitHub.

## Files

| File | Purpose |
| ---- | ------- |
| [datefromname.py](../datefromname.py) | All the date logic: parsing names, reading and writing dates, deciding what to do. It has no GUI code and also works as a command-line tool. |
| [app.py](../app.py) | The tkinter window, the entry point for the `.exe`. It's a thin layer over `datefromname`. |
| [updater.py](../updater.py) | Checks GitHub Releases and swaps in the new `.exe`. |
| [_version.py](../_version.py) | `VERSION = "dev"` in the repo. The release workflow overwrites it with the tag. |
| [tests/test_datefromname.py](../tests/test_datefromname.py) | Unit tests. These build real JPEG and MP4 files in a temp folder. |
| [.github/workflows/release.yml](../.github/workflows/release.yml) | On a `v*` tag, it tests, builds and publishes the release. |

## How a file is processed

`plan_folder()` makes two passes over the folder. Nothing is written until
`apply_plan()` is called.

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

| Situation | Action | Why |
| --------- | ------ | --- |
| **No date in the name** (camera files) | Keep the date inside | It's the only date there is. |
| The date inside the file **agrees** with the name | Keep it | It's already right. For timed names "agrees" means within 14 hours, to allow for time zones. For date-only names it means the same day. |
| The date inside is **more than a day older** than the name | Keep it | Probably an edited or re-shared copy of an older photo, so the date inside is the real one. |
| No date inside, or a **later** one | Write the name's date | A later date is usually the download or re-encode time. |

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

A CSV log of every file is **optional and off by default**, so logs don't pile
up on the user's PC. It's saved only when the "Also save a list of the changes"
tick box is ticked. It goes in a `FixPhotoDates logs` folder next to the `.exe`
(or next to `app.py` when run from source), named
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

```
git tag v1.1.0
git push origin v1.1.0
```

The workflow runs on `windows-latest` (about 1 minute):

1. Installs the dependencies and runs the tests. If they fail, nothing is
   released.
2. Writes the tag into `_version.py`.
3. Runs `pyinstaller --onefile --windowed --name FixPhotoDates app.py`.
4. Runs `gh release create` with the exe attached and auto-generated notes.

Each new tag must be numerically higher than the last, or installed copies
won't offer it.

This link always gives the newest version, so it's the one to give to users:
https://github.com/TomZandt/DateFromName/releases/latest/download/FixPhotoDates.exe

## Working locally

```
pip install -r requirements.txt -r requirements-dev.txt
python -m unittest discover -s tests -v
python app.py                                  # the window
python datefromname.py "D:\Photos"             # preview on the command line
python datefromname.py "D:\Photos" --apply     # fix on the command line
```

To build the exe locally:

```
pyinstaller --onefile --windowed --name FixPhotoDates app.py
```

The output goes to `dist/`. `build/`, `dist/` and `*.spec` are git-ignored. A
local build reports its version as `dev` and never updates itself.

Always try changes on a **copy** of a photo folder. The app changes files in
place and has no undo.

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

- **No undo.** The optional CSV log records the old and new dates, but nothing
  reads it back.
- **The exe is unsigned,** so the first run shows SmartScreen's "Windows
  protected your PC". A code-signing certificate would remove this.
- **WhatsApp times are made up** (midday plus order number) unless the real
  time survived in the file's modified date.
- **GoPro and some other cameras store local time in the MP4 header** where
  the standard says UTC. For those files with no date in the name, the Windows
  dates can be off by the time-zone difference (the order is still right).
- **The pattern for names that are just a timestamp** (`^\d{10}`) would also
  treat any other 10- or 13-digit name as a date, as long as it falls in a
  plausible year.
- **RAW dates inside the file aren't read** (`.CR2`, `.NEF` and so on). A RAW
  file with no date in its name is skipped.
- **iPhone screenshots** (`IMG_1234.PNG`) have no date in the name or inside
  the file, so they're skipped.
- **Only JPEG and MP4-family files get a date inside the file.** For other
  types, only the Windows created and modified dates change, which some apps
  ignore.
- **The update needs write access to the exe's folder.** That's fine on the
  Desktop or in Downloads. If the exe is in `Program Files`, the app falls
  back to opening the releases page.
- **The workflow uses `actions/checkout@v4` and `actions/setup-python@v5`.**
  GitHub warns these use the deprecated Node 20. It still works. Bump them to
  their Node 24 versions when convenient.
