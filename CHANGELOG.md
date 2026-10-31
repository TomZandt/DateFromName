# Changelog

What changed in each version of Fix Photo Dates. See the
[README](README.md) for how the app works now. Versions follow
[Semantic Versioning](CONTRIBUTING.md#versions-semantic-versioning).

## Unreleased

- **The window is split into three tabs**, one per job: **Fix dates**,
  **Organise** and **Renumber**. Each reads top to bottom: choose a folder,
  check the list, then click the button under it.
- **Fix dates** now only changes dates. Adding the date to names and month
  folders moved to the new **Organise** tab.
- **Organise can undo** what it does: remove the date from the start of names,
  and take photos out of month folders.
- **Fix:** choosing a month folder itself and putting photos into month folders
  made `2026_08\2026_08`. The month folders now go beside it.
- **New Renumber tab** closes the gaps in the numbers after photos are deleted,
  keeping the order.
- **Colours in the preview:** the date added to a name is blue and the month
  folder is green, matching the choices above the list.
- **Fix:** files whose only date is the one this app added
  (e.g. `2026_09_02_0001_DSC_1234.JPG`) were skipped. They now use that date.
- Added the MIT licence.
- For developers: a much bigger test suite (window, updater, error handling),
  tests on every push, commit message and versioning guidelines, and
  checklists for before and after a release and after merging.

## v1.2.0 (31 October 2026)

- **Many more file name formats:** Samsung, OnePlus/Oppo, DJI, Xiaomi and
  Windows screenshots, Telegram, Signal, Dropbox, dash cams, Facebook,
  iPhone screen recordings, and WhatsApp desktop times with AM/PM.
- **Camera, GoPro and iPhone files** with no date in the name now use the date
  inside the file, including iPhone HEIC photos.
- **Option to add the date to the start of file names**
  (`YYYY_MM_DD_####_`), numbered from `0000` each month.
- **Option to put photos into month folders** (`YYYY_MM`).

## v1.1.1 (31 October 2026)

- **Fix:** updating no longer shows a "Failed to remove temporary directory"
  warning. Updating *from* v1.0.0 or v1.1.0 still shows it once.

## v1.1.0 (31 October 2026)

- **The change log is now optional** and off by default. When ticked, it's
  saved in a `FixPhotoDates logs` folder.

## v1.0.0 (31 October 2026)

- First release: fixes dates from WhatsApp and Google Pixel file names, with a
  preview before anything changes, and updates itself from GitHub.
