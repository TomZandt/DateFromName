# Fix Photo Dates

Photos and videos downloaded from Google Photos (especially WhatsApp ones) often
lose their "Date taken", so Windows shows the day they were downloaded instead.
Their file names still contain the real date. This Windows app puts that date
back. It can also organise the photos by date and tidy up the numbering
afterwards.

This README is the starting point for everything about the project. Every
other document is linked from [Documentation](#documentation) at the bottom.

## Installing (no setup needed)

1. Download **FixPhotoDates.exe**. This link always gives the newest version:
   https://github.com/TomZandt/DateFromName/releases/latest/download/FixPhotoDates.exe
2. Move it somewhere easy to find, such as the Desktop, and double-click it.
   - The first time, Windows may show *"Windows protected your PC"*. Click
     **More info**, then **Run anyway**. This only happens once.

When a new version is out, a yellow bar appears at the top of the app. Click
**Update now** and it updates and restarts by itself.

## Using it

The app has three tabs, one for each job. They all work the same way:

1. Click **1. Choose photo folder** and pick the folder. Subfolders are
   included. The app lists what it *would* change, and nothing changes yet.
2. Check the list, then click the **2.** button under it.

| Tab | What it changes | What it never changes |
| --- | --------------- | --------------------- |
| [Fix dates](#fix-dates) | The date inside each file and the Windows created/modified dates | Names, folders, the pictures themselves |
| [Organise](#organise) | File names (a date at the start) and month folders, or undoing either | Dates |
| [Renumber](#renumber) | The four-digit number at the start of names that already have one | Dates, folders, anything else in the name |

**Save a list of the changes** (at the bottom of the window, for any tab)
saves a CSV record in a `FixPhotoDates logs` folder next to the app. It's off
by default so records don't build up.

### Fix dates

The date comes from the file name. These are the names it recognises:

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
| Organised by this app | `2026_08_22_0003_DSC_1234.JPG` | The date at the start, if the rest of the name has none |
| iPhone | `IMG_1234.HEIC`, `IMG_1234.JPG`, `IMG_1234.MOV` | No date in the name, so the date inside the file is used to fix the Windows dates |
| Cameras, GoPro | `DSC_1234.JPG`, `P1010123.JPG`, `GX010123.MP4` | Same: the date inside the file |
| Anything else with a date | `holiday 2026-08-22.jpg` | The date at midday |

For each file:

- **The date inside the file already matches the name**: the date is left
  alone. Only the Windows created/modified dates are lined up with it.
- **No date inside the file, or a later one** (e.g. the download date): the date
  from the name is written in. JPEGs get "Date taken" and MP4/MOV get "Media
  created". The picture data is not re-encoded.
- **An older date inside the file** (e.g. an edited copy of an old photo): kept,
  because it's more likely to be the real one.
- **WhatsApp file whose modified date is already the right day**: that real
  time is kept instead of midday.
- **No date in the name** (e.g. a camera's `DSC_1234.JPG`): the date inside
  the file is used to fix the Windows dates. If there's no date inside either,
  the file is left alone.

### Organise

Both choices start on "Leave". Changing one updates the list straight away. In
the list, the date added to the name is **blue** and the month folder is
**green**.

- **Date at the start of the name**
  - **Add it (and renumber).** For example, `IMG-20260822-WA0002.jpeg` becomes
    `2026_08_22_0000_IMG-20260822-WA0002.jpeg`. The four-digit number counts
    from `0000` for the oldest photo of each month in each folder, so sorting
    by name also sorts by date. Running it again renumbers, which closes any
    gaps and fits new photos into the order.
  - **Remove it.** Takes the date and number back off.
- **Month folders**
  - **Put photos into month folders.** Every dated photo in the chosen folder
    (including subfolders) moves into `<chosen folder>\2026_08\` and so on.
    Photos with no date stay where they are.
  - **Take photos out of month folders.** Moves photos out of any `YYYY_MM`
    folder into the folder above it.

If two files would end up with the same name, the second gets ` (2)` added
rather than overwriting. Folders left empty are removed.

### Renumber

After deleting unwanted photos there are gaps in the numbers (`0000`, `0003`,
`0007`…). Renumber closes them: within each month in each folder, the numbered
photos become `0000`, `0001`, `0002`… in the same order as before. Files
without a number are left alone. It doesn't read the photos, so it's quick.

## Good to know

- **Try it on a copy first.** Date fixes can't be undone. Organising can be
  reversed on the Organise tab, but taking photos out of month folders can't
  put them back in the subfolders they came from.
- **WhatsApp times are made up** (midday plus the order number), because
  WhatsApp names only have the date. The real time is kept if it survived.
- **GoPro videos** can end up a few hours out, because GoPro stores local time
  where the standard expects UTC. The order is still right.
- **Some files are left alone:** iPhone screenshots (`IMG_1234.PNG`) and camera
  RAW files (`.CR2`, `.NEF` and so on) with no date in the name, because the
  app can't find a date for them.
- **Only JPEG and MP4/MOV files get the date written inside them.** Other types
  (PNG, HEIC and so on) only get their Windows created/modified dates fixed,
  which some apps ignore.
- **For updates to install by themselves,** keep the app somewhere you can save
  files, such as the Desktop or Downloads. If it can't update itself, it opens
  the download page instead.

## Documentation

| Document | For |
| -------- | --- |
| This README | Using the app: installing, the three tabs and their rules |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each version |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Developers: how it works inside, running from source, building, releasing, developer-only limitations |
| [LICENSE](LICENSE) | The licence |

## Licence

[MIT](LICENSE): free to use, copy and change, with no warranty. The app bundles
Python, Tk and [piexif](https://github.com/hMatoba/Piexif) (MIT), and is built
with PyInstaller, whose licence allows the result to be distributed under any
licence.
