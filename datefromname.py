"""Fix photo and video dates using the date in the file name.

Photos downloaded from Google Photos (especially WhatsApp ones) often lose
their "Date taken", so Windows shows the download date instead. The file
name usually still has the real date, e.g.

    IMG-20260822-WA0004.jpeg     WhatsApp photo, date only (+ order number)
    VID-20260825-WA0029.mp4      WhatsApp video, date only (+ order number)
    PXL_20260822_092200562.jpg   Google Pixel, date and time in UTC
    IMG_20260822_123456.jpg      Most other phones, date and local time

For each file we compare the date stored inside the file with the date in
its name. If it is already right we leave it alone; otherwise we write the
name's date into the file (JPEG "Date taken", MP4 "Media created") and set
the Windows created/modified dates to match.

Command line use (the GUI in app.py uses the same functions):

    python datefromname.py "D:\\Photos"           preview only
    python datefromname.py "D:\\Photos" --apply   make the changes
"""

import argparse
import csv
import os
import re
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import piexif

JPEG_EXTS = {".jpg", ".jpeg"}
MP4_EXTS = {".mp4", ".mov", ".m4v", ".3gp"}
MEDIA_EXTS = JPEG_EXTS | MP4_EXTS | {
    ".png", ".gif", ".webp", ".heic", ".heif", ".avi", ".mkv",
    ".opus", ".m4a", ".mp3", ".aac", ".wav",
}

DATE_ONLY, LOCAL_TIME, UTC_TIME = "date only", "local time", "UTC time"

EXIF_FORMAT = "%Y:%m:%d %H:%M:%S"
QUICKTIME_EPOCH = datetime(1904, 1, 1)

# A timed name and the date inside the file "agree" if they are within this
# much of each other, which covers any time zone difference.
TIME_ZONE_SLACK = timedelta(hours=14)

# First match wins, so the most specific patterns come first.
PATTERNS = [
    # WhatsApp: IMG-20260822-WA0004.jpeg, VID-20260825-WA0029.mp4
    (re.compile(r"^(?:IMG|VID|AUD|PTT|STK|DOC)-(\d{4})(\d{2})(\d{2})-WA(\d+)", re.I), DATE_ONLY),
    # Google Pixel: PXL_20260822_092200562.MP.jpg (time is UTC)
    (re.compile(r"^PXL_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", re.I), UTC_TIME),
    # WhatsApp desktop and Mac screenshots: "WhatsApp Image 2026-08-22 at 12.34.56"
    (re.compile(r"(\d{4})-(\d{2})-(\d{2}) at (\d{1,2})\.(\d{2})\.(\d{2})"), LOCAL_TIME),
    # Most phones and screenshots: IMG_20260822_123456, Screenshot_20260822-123456
    (re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})(?!\d)"), LOCAL_TIME),
    # Anything else with a date in it: 2026-08-22, 20260822
    (re.compile(r"(?<!\d)(\d{4})-?(\d{2})-?(\d{2})(?!\d)"), DATE_ONLY),
]


@dataclass
class NameDate:
    when: datetime  # naive; UTC for UTC_TIME names, local time otherwise
    kind: str
    seq: int = 0    # WhatsApp order number, used to keep same-day photos in order


@dataclass
class Plan:
    path: str
    name_date: NameDate
    embedded: datetime | None  # date stored inside the file, local time
    target: datetime | None = None
    write_embedded: bool = False
    set_file_times: bool = False
    status: str = ""
    error: str = ""

    @property
    def needs_change(self):
        return self.write_embedded or self.set_file_times


def parse_name(filename):
    """Return the NameDate found in a file name, or None."""
    stem = os.path.splitext(filename)[0]
    for pattern, kind in PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        nums = [int(g) for g in match.groups()]
        try:
            if kind == DATE_ONLY:
                when = datetime(*nums[:3])
                seq = nums[3] if len(nums) > 3 else 0
            else:
                when = datetime(*nums[:6])
                seq = 0
        except ValueError:
            continue
        if 1990 <= when.year <= datetime.now().year + 1:
            return NameDate(when, kind, seq)
    return None


def utc_to_local(when):
    return datetime.fromtimestamp(when.replace(tzinfo=timezone.utc).timestamp())


def local_to_utc(when):
    return datetime.fromtimestamp(when.timestamp(), timezone.utc).replace(tzinfo=None)


# --- JPEG ------------------------------------------------------------------

def read_jpeg_date(path):
    try:
        exif = piexif.load(path)
    except Exception:
        return None
    for tag in (piexif.ExifIFD.DateTimeOriginal, piexif.ExifIFD.DateTimeDigitized):
        raw = exif.get("Exif", {}).get(tag)
        if raw:
            try:
                return datetime.strptime(raw.decode("ascii", "ignore").strip("\x00 ")[:19], EXIF_FORMAT)
            except ValueError:
                pass
    return None


def write_jpeg_date(path, when):
    """Set "Date taken" without re-encoding the picture."""
    exif = piexif.load(path)
    stamp = when.strftime(EXIF_FORMAT).encode("ascii")
    exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = stamp
    exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = stamp
    exif["0th"][piexif.ImageIFD.DateTime] = stamp
    piexif.insert(piexif.dump(exif), path)


# --- MP4 / MOV -------------------------------------------------------------

def _boxes(f, start, end):
    """Yield (type, payload_start, box_end) for each box between start and end."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        size, kind = struct.unpack(">I4s", f.read(8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header:
            return
        yield kind, pos + header, pos + size
        pos += size


def _header_time_fields(f, start, end):
    """Yield (box type, offset, width) of the creation time in each movie header."""
    for kind, payload, box_end in list(_boxes(f, start, end)):
        if kind in (b"mvhd", b"tkhd", b"mdhd"):
            f.seek(payload)
            width = 8 if f.read(1)[0] == 1 else 4
            yield kind, payload + 4, width  # creation time; modification time follows
        elif kind in (b"moov", b"trak", b"mdia"):
            yield from _header_time_fields(f, payload, box_end)


def _mp4_fields(f):
    return list(_header_time_fields(f, 0, f.seek(0, os.SEEK_END)))


def read_mp4_date(path):
    try:
        with open(path, "rb") as f:
            for kind, offset, width in _mp4_fields(f):
                if kind == b"mvhd":
                    f.seek(offset)
                    seconds = int.from_bytes(f.read(width), "big")
                    when = QUICKTIME_EPOCH + timedelta(seconds=seconds)
                    return utc_to_local(when) if when.year >= 1990 else None
    except (OSError, struct.error, IndexError, OverflowError, ValueError):
        pass
    return None


def write_mp4_date(path, when):
    """Set "Media created" by patching the header times in place."""
    seconds = int((local_to_utc(when) - QUICKTIME_EPOCH).total_seconds())
    with open(path, "r+b") as f:
        fields = _mp4_fields(f)
        if not fields:
            raise ValueError("no movie header found")
        for _, offset, width in fields:
            f.seek(offset)
            f.write(seconds.to_bytes(width, "big") * 2)  # creation and modification


# --- Windows file times ----------------------------------------------------

def get_file_times(path):
    st = os.stat(path)
    created = getattr(st, "st_birthtime", st.st_ctime)
    return datetime.fromtimestamp(created), datetime.fromtimestamp(st.st_mtime)


def set_file_times(path, when):
    """Set the created and modified dates shown in File Explorer."""
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    ticks = int(stamp * 10_000_000) + 116444736000000000  # 100ns ticks since 1601
    filetime = wintypes.FILETIME(ticks & 0xFFFFFFFF, ticks >> 32)
    handle = kernel32.CreateFileW(path, 0x100, 7, None, 3, 0x02000000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel32.SetFileTime(handle, ctypes.byref(filetime), None, None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)


# --- Planning --------------------------------------------------------------

def read_embedded_date(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in JPEG_EXTS:
        return read_jpeg_date(path)
    if ext in MP4_EXTS:
        return read_mp4_date(path)
    return None


def find_media(folder, recurse=True):
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")] if recurse else []
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() in MEDIA_EXTS:
                yield os.path.join(root, name)


def _agrees(embedded, name_date):
    if name_date.kind == DATE_ONLY:
        return embedded.date() == name_date.when.date()
    return abs(embedded - name_date.when) <= TIME_ZONE_SLACK


def _pixel_offsets(plans):
    """Learn the camera's time zone from Pixel photos that still have their date."""
    offsets = []
    for plan in plans:
        nd = plan.name_date
        if nd.kind == UTC_TIME and plan.embedded and _agrees(plan.embedded, nd):
            quarters = round((plan.embedded - nd.when) / timedelta(minutes=15))
            offsets.append((nd.when, timedelta(minutes=15 * quarters)))
    return offsets


def _utc_name_to_local(when, offsets):
    if offsets:
        _, offset = min(offsets, key=lambda item: abs(item[0] - when))
        return when + offset
    return utc_to_local(when)


def plan_folder(folder, recurse=True, progress=None):
    """Work out what to do with every media file. Returns (plans, skipped)."""
    paths = list(find_media(folder, recurse))
    plans, skipped = [], []
    for i, path in enumerate(paths, 1):
        name_date = parse_name(os.path.basename(path))
        if name_date is None:
            skipped.append(path)
        else:
            plans.append(Plan(path, name_date, read_embedded_date(path)))
        if progress:
            progress(i, len(paths))

    offsets = _pixel_offsets(plans)
    for plan in plans:
        _decide(plan, offsets)
    return plans, skipped


def _decide(plan, offsets):
    nd, embedded = plan.name_date, plan.embedded
    ext = os.path.splitext(plan.path)[1].lower()
    created, modified = get_file_times(plan.path)

    if embedded and _agrees(embedded, nd):
        plan.target = embedded
        plan.status = "Already correct"
    elif embedded and embedded.date() < nd.when.date() - timedelta(days=1):
        # An older date inside the file is probably the real one (e.g. an edited copy).
        plan.target = embedded
        plan.status = "Kept date inside file (older than name)"
    else:
        if nd.kind == DATE_ONLY:
            if modified.date() == nd.when.date():
                plan.target = modified  # the real time survived, keep it
            else:
                # No time in the name: midday, nudged by the WhatsApp number to keep the order.
                plan.target = nd.when.replace(hour=12) + timedelta(seconds=nd.seq)
        elif nd.kind == UTC_TIME:
            plan.target = _utc_name_to_local(nd.when, offsets)
        else:
            plan.target = nd.when
        plan.write_embedded = ext in JPEG_EXTS | MP4_EXTS
        plan.status = "Wrong date replaced" if embedded else "Date added"

    slack = timedelta(seconds=2)
    plan.set_file_times = abs(modified - plan.target) > slack or abs(created - plan.target) > slack
    if not plan.write_embedded and plan.set_file_times and plan.status.startswith(("Already", "Kept")):
        plan.status += ", file dates updated"


def apply_plan(plan):
    """Make the changes for one file. Records any error on the plan."""
    ext = os.path.splitext(plan.path)[1].lower()
    try:
        if plan.write_embedded:
            if ext in JPEG_EXTS:
                write_jpeg_date(plan.path, plan.target)
            else:
                write_mp4_date(plan.path, plan.target)
    except Exception as exc:
        plan.error = f"Could not write date inside file ({exc}); file dates still set"
    try:
        set_file_times(plan.path, plan.target)
    except Exception as exc:
        plan.error = f"Could not change file dates ({exc})"


def write_log(plans, log_path):
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["File", "Date in name", "Date inside file before", "New date", "Result", "Error"])
        for p in plans:
            writer.writerow([
                p.path,
                p.name_date.when.strftime("%d/%m/%Y %H:%M:%S") + f" ({p.name_date.kind})",
                p.embedded.strftime("%d/%m/%Y %H:%M:%S") if p.embedded else "",
                p.target.strftime("%d/%m/%Y %H:%M:%S") if p.target else "",
                p.status,
                p.error,
            ])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fix photo/video dates from their file names.")
    parser.add_argument("folder")
    parser.add_argument("--apply", action="store_true", help="make the changes (default is preview only)")
    parser.add_argument("--no-recurse", action="store_true", help="ignore subfolders")
    args = parser.parse_args(argv)

    plans, skipped = plan_folder(args.folder, recurse=not args.no_recurse)
    changes = [p for p in plans if p.needs_change]
    for p in changes:
        print(f"{os.path.relpath(p.path, args.folder):45} -> {p.target:%d/%m/%Y %H:%M:%S}  {p.status}")
    print(f"\n{len(plans) - len(changes)} already correct, {len(changes)} to fix, "
          f"{len(skipped)} with no date in the name.")

    if args.apply:
        for p in changes:
            apply_plan(p)
            if p.error:
                print(f"{p.path}: {p.error}", file=sys.stderr)
        print("Done.")
    elif changes:
        print("Preview only. Run again with --apply to make the changes.")


if __name__ == "__main__":
    main()
