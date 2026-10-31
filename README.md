# Fix Photo Dates

Photos and videos downloaded from Google Photos (especially WhatsApp ones) often
lose their "Date taken", so Windows shows the day they were downloaded instead.
Their file names still contain the real date. This app puts that date back.

## Installing and using it (no setup needed)

1. Download **FixPhotoDates.exe**:
   https://github.com/TomZandt/DateFromName/releases/latest/download/FixPhotoDates.exe
2. Move it somewhere easy to find, such as the Desktop, and double-click it.
   - The first time, Windows may show *"Windows protected your PC"*. Click
     **More info**, then **Run anyway**. This only happens once.
3. Click **Choose photo folder** and pick the folder with the photos.
4. The app lists what it found. Click **Fix dates**.

When a new version is out, a yellow bar appears at the top of the app. Click
**Update now** and it updates and restarts by itself.

## What it does

| Source | Example names | Date used |
| ------ | ------------- | --------- |
| WhatsApp (phone) | `IMG-20260822-WA0004.jpeg`, `VID-20260825-WA0029.mp4` | The date at midday, nudged by the number so photos stay in order |
| WhatsApp (desktop) | `WhatsApp Image 2026-08-22 at 9.05.01 PM.jpeg` | Date and time (24-hour or AM/PM) |
| Google Pixel | `PXL_20260822_092200562.MP.jpg`, `PXL_..._.TS.mp4` | Date and time. The name uses UTC, so it's converted to the time zone of nearby Pixel photos |
| Most Android (Motorola, Xiaomi, Huawei, Sony, Nokia, older Pixel) | `IMG_20260822_123456.jpg`, `VID_20260822_123456.mp4`, `MVIMG_...` | Date and time |
| Samsung, LG | `20260822_123456.jpg`, `20260822_123456(0).jpg` | Date and time |
| OnePlus, Oppo, Realme | `IMG20260822123456.jpg`, `VID20260822123456.mp4` | Date and time |
| DJI drones | `DJI_20260822123456_0001_D.JPG` | Date and time |
| Screenshots | `Screenshot_20260822-123456.png`, `Screenshot_2026-08-22-12-34-56-123_com.whatsapp.jpg`, `Screenshot 2026-08-22 123456.png` | Date and time |
| Telegram, Signal | `photo_2026-08-22_12-34-56.jpg`, `photo_1@22-08-2026_12-34-56.jpg`, `signal-2026-08-22-123456.jpg` | Date and time |
| Dropbox, dash cams | `2026-08-22 12.34.56.jpg`, `2026_0822_123456_001.MP4` | Date and time |
| Facebook/Messenger, iPhone screen recordings | `FB_IMG_1787398496123.jpg`, `RPReplay_Final1787398496.MP4` | The timestamp in the name |
| iPhone | `IMG_1234.HEIC`, `IMG_1234.JPG`, `IMG_1234.MOV` | No date in the name, so the date inside the file is used to fix the Windows dates |
| Cameras, GoPro | `DSC_1234.JPG`, `P1010123.JPG`, `GX010123.MP4` | Same: the date inside the file |
| Anything else with a date | `holiday 2026-08-22.jpg` | The date at midday |

For each file:

- **The date inside the file already matches the name**: the date is left alone.
  Only the Windows created/modified dates are lined up with it.
- **No date inside the file, or a later one** (e.g. the download date): the date
  from the name is written in. JPEGs get "Date taken" and MP4/MOV get "Media
  created". The picture data is not re-encoded.
- **An older date inside the file** (e.g. an edited copy of an old photo): kept,
  because it is more likely to be the real one.
- **WhatsApp file whose modified date is already the right day**: that real
  time is kept instead of midday.
- **No date in the name** (e.g. a camera's `DSC_1234.JPG`): the date inside
  the file is used to fix the Windows dates. If there's no date inside either,
  the file is skipped.

## Options

All three tick boxes are off by default. Ticking one updates the list straight
away, so you can see the result before clicking **Fix**.

- **Add the date to the start of each file name.** For example,
  `IMG-20260822-WA0002.jpeg` becomes `2026_08_22_0000_IMG-20260822-WA0002.jpeg`.
  The four-digit number counts from `0000` for the oldest photo of each month,
  so sorting by name also sorts by date. Running it again only renumbers if
  photos have been added.
- **Put the photos into a folder for each month.** Every dated photo in the
  chosen folder (including subfolders) moves into `<chosen folder>\2026_08\`
  and so on. If two files have the same name, the second gets ` (2)` added.
  Folders left empty are removed. Photos with no date stay where they are.
- **Save a list of the changes.** A CSV log is saved in a `FixPhotoDates logs`
  folder next to the exe.

## Renumbering after deleting photos

After deleting unwanted photos there are gaps in the numbers (`0000`, `0003`,
`0007`…). Click **Renumber a folder**, choose the folder (subfolders are
included), check the list and click **Renumber**. Within each month in each
folder, the numbered photos become `0000`, `0001`, `0002`… in the same order as
before. Nothing else changes: no dates, no moving, and files without a number
are left alone.

## Development

See the **[developer guide](docs/DEVELOPMENT.md)** for how it works, how
self-update works, releasing, and known limitations. Quick start:

```
pip install -r requirements.txt -r requirements-dev.txt
python app.py                                  # the window
python datefromname.py "D:\Photos"             # command line preview
python datefromname.py "D:\Photos" --apply     # command line fix
python datefromname.py "D:\Photos" --rename --month-folders --apply
python -m unittest discover -s tests
```

### Releasing an update

```
git tag v1.1.0
git push origin v1.1.0
```

The [release workflow](.github/workflows/release.yml) runs the tests, builds
`FixPhotoDates.exe` with the version stamped in and publishes a GitHub release.
Copies already installed will offer the update the next time they are opened.
Version tags must be numbers only (`v1.2.0`) and go up each time.
