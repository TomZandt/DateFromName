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

| File name                      | Date used                                             |
| ------------------------------ | ----------------------------------------------------- |
| `IMG-20260822-WA0004.jpeg`     | WhatsApp: the date at midday, nudged by the number so photos stay in order |
| `VID-20260825-WA0029.mp4`      | Same, for WhatsApp videos                             |
| `PXL_20260822_092200562.jpg`   | Google Pixel: date and time (UTC, converted to the time zone of nearby Pixel photos) |
| `IMG_20260822_123456.jpg`, `Screenshot_20260822-123456.png` | Date and time in the name |
| anything with `2026-08-22` / `20260822` in it | The date at midday            |

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
- **No date in the name**: skipped.

To keep a record, tick **Also save a list of the changes** before clicking
**Fix dates**. A CSV log is then saved in a `FixPhotoDates logs` folder next
to the exe. This is off by default so logs don't build up.

## Development

See the **[developer guide](docs/DEVELOPMENT.md)** for how it works, how
self-update works, releasing, and known limitations. Quick start:

```
pip install -r requirements.txt -r requirements-dev.txt
python app.py                                  # the window
python datefromname.py "D:\Photos"             # command line preview
python datefromname.py "D:\Photos" --apply     # command line fix
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
