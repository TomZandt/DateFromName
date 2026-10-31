"""Fix photo and video dates using the date in the file name.

Photos downloaded from Google Photos (especially WhatsApp ones) often lose
their "Date taken", so Windows shows the download date instead. The file
name usually still has the real date, e.g.

    IMG-20260822-WA0004.jpeg     WhatsApp photo, date only (+ order number)
    VID-20260825-WA0029.mp4      WhatsApp video, date only (+ order number)
    PXL_20260822_092200562.jpg   Google Pixel, date and time in UTC
    IMG_20260822_123456.jpg      Most other phones, date and local time
    DSC_1234.JPG                 Cameras: no date in the name, use the one inside

(See PATTERNS for the full list of name layouts.) For each file we compare the date stored inside the file with the date in
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

JPEG_EXTS = {".jpg", ".jpeg", ".jfif"}
MP4_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".3g2"}
HEIC_EXTS = {".heic", ".heif"}  # date is read, never written
MEDIA_EXTS = JPEG_EXTS | MP4_EXTS | HEIC_EXTS | {
    ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff",
    ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf",
    ".avi", ".mkv", ".mts", ".m2ts", ".wmv", ".mpg", ".mpeg", ".webm",
    ".opus", ".m4a", ".mp3", ".aac", ".wav",
}

DATE_ONLY, LOCAL_TIME, UTC_TIME = "date only", "local time", "UTC time"

EXIF_FORMAT = "%Y:%m:%d %H:%M:%S"
QUICKTIME_EPOCH = datetime(1904, 1, 1)

# A timed name and the date inside the file "agree" if they are within this
# much of each other, which covers any time zone difference.
TIME_ZONE_SLACK = timedelta(hours=14)

# First match wins, so the most specific patterns come first. Group names:
# y m d = date, H M S = time, ampm = 12-hour clock, seq = WhatsApp order
# number, epoch = seconds since 1970 (UTC).
PATTERNS = [(re.compile(pattern, re.I), kind) for pattern, kind in [
    # WhatsApp: IMG-20260822-WA0004.jpeg, VID-20260825-WA0029.mp4
    (r"^(?:IMG|VID|AUD|PTT|STK|DOC)-(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})-WA(?P<seq>\d+)", DATE_ONLY),
    # Google Pixel: PXL_20260822_092200562.MP.jpg (time is UTC)
    (r"^PXL_(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})_(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})", UTC_TIME),
    # Facebook/Messenger FB_IMG_1661234567890.jpg, iPhone screen recordings
    # RPReplay_Final1661234567.mp4, and names that are only a timestamp
    (r"^(?:FB_IMG_|RPReplay_Final)?(?P<epoch>\d{10})(?:\d{3})?(?!\d)", UTC_TIME),
    # WhatsApp desktop and Mac: "WhatsApp Image 2026-08-22 at 12.34.56", "... at 9.05.01 PM"
    (r"(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2}) at (?P<H>\d{1,2})[.:](?P<M>\d{2})[.:](?P<S>\d{2})"
     r"(?:\s?(?P<ampm>[AP]M))?", LOCAL_TIME),
    # Day first, old Telegram: photo_123@22-08-2026_12-34-56.jpg
    (r"(?<!\d)(?P<d>\d{2})-(?P<m>\d{2})-(?P<y>\d{4})_(?P<H>\d{2})-(?P<M>\d{2})-(?P<S>\d{2})(?!\d)", LOCAL_TIME),
    # Date and time in most other layouts:
    #   IMG_20260822_123456 (most Android), 20260822_123456 (Samsung),
    #   IMG20260822123456 (OnePlus/Oppo), DJI_20260822123456_0001 (DJI),
    #   Screenshot_2026-08-22-12-34-56 (Xiaomi), photo_2026-08-22_12-34-56 (Telegram),
    #   2026-08-22 12.34.56 (Dropbox), Screenshot 2026-08-22 123456 (Windows),
    #   signal-2026-08-22-123456 (Signal), 2026_0822_123456 (dash cams)
    (r"(?<!\d)(?P<y>\d{4})[-_.]?(?P<m>\d{2})[-_.]?(?P<d>\d{2})[ _T-]?"
     r"(?P<H>\d{2})[-_.:h]?(?P<M>\d{2})[-_.:m]?(?P<S>\d{2})(?:\d{3})?(?!\d)", LOCAL_TIME),
    # Anything else with a date in it: 2026-08-22, 20260822
    (r"(?<!\d)(?P<y>\d{4})[-_.]?(?P<m>\d{2})[-_.]?(?P<d>\d{2})(?!\d)", DATE_ONLY),
]]

# Optional prefix added by plan_new_paths: 2026_08_22_0000_IMG-20260822-WA0002.jpeg
PREFIX = re.compile(r"^(?P<y>\d{4})_(?P<m>\d{2})_(?P<d>\d{2})_(?P<n>\d{4})_")


@dataclass
class NameDate:
    when: datetime  # naive; UTC for UTC_TIME names, local time otherwise
    kind: str
    seq: int = 0    # WhatsApp order number, used to keep same-day photos in order


@dataclass
class Plan:
    path: str
    name_date: NameDate | None  # None for camera names like DSC_1234.JPG
    embedded: datetime | None   # date stored inside the file, local time
    target: datetime | None = None
    write_embedded: bool = False
    set_file_times: bool = False
    status: str = ""
    error: str = ""
    new_path: str | None = None  # set by plan_new_paths when renaming or moving

    @property
    def fixes_date(self):
        return self.write_embedded or self.set_file_times

    @property
    def needs_change(self):
        return self.fixes_date or bool(self.new_path)


def parse_name(filename):
    """Return the NameDate found in a file name, or None."""
    stem = os.path.splitext(filename)[0]
    prefix = PREFIX.match(stem)
    if prefix:
        stem = stem[prefix.end():]  # look at the original name first; it may have a time
    for pattern, kind in PATTERNS:
        for match in pattern.finditer(stem):
            when = _match_to_datetime(match, kind)
            if when and 1990 <= when.year <= datetime.now().year + 1:
                seq = match.groupdict().get("seq")
                return NameDate(when, kind, int(seq) if seq else 0)
    if prefix:
        # e.g. 2026_09_02_0001_DSC_1234.JPG: only our prefix has the date.
        try:
            when = datetime(int(prefix["y"]), int(prefix["m"]), int(prefix["d"]))
            return NameDate(when, DATE_ONLY, int(prefix["n"]))
        except ValueError:
            pass
    return None


def _match_to_datetime(match, kind):
    parts = match.groupdict()
    num = {k: int(v) for k, v in parts.items() if v and v.isdigit()}
    try:
        if "epoch" in num:
            return datetime.fromtimestamp(num["epoch"], timezone.utc).replace(tzinfo=None)
        if kind == DATE_ONLY:
            return datetime(num["y"], num["m"], num["d"])
        hour = num["H"]
        if parts.get("ampm"):
            hour = hour % 12 + (12 if parts["ampm"].upper() == "PM" else 0)
        return datetime(num["y"], num["m"], num["d"], hour, num["M"], num["S"])
    except (ValueError, OverflowError, OSError):
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
    return _exif_date(exif)


def _exif_date(exif):
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


# --- HEIC (iPhone) -----------------------------------------------------------
# HEIC uses the same box layout as MP4. The EXIF block is an item listed in
# meta/iinf, and meta/iloc says where its bytes are. We only read it: iPhone
# photos keep their date, so they just need the Windows dates lining up.

def _full_box(f, payload):
    f.seek(payload)
    return f.read(1)[0], payload + 4  # version, start of contents


def _read_uint(f, size):
    return int.from_bytes(f.read(size), "big") if size else 0


def _heic_exif_item(f, start, end):
    """Return the item ID of the EXIF block listed in iinf."""
    version, pos = _full_box(f, start)
    count_size = 2 if version == 0 else 4
    for kind, payload, _ in _boxes(f, pos + count_size, end):
        if kind != b"infe":
            continue
        version, pos = _full_box(f, payload)
        if version < 2:
            continue
        f.seek(pos)
        item_id = _read_uint(f, 2 if version == 2 else 4)
        f.read(2)  # protection index
        if f.read(4) == b"Exif":
            return item_id
    return None


def _heic_item_location(f, start, item):
    """Return (offset, length) of an item's first extent from iloc."""
    version, pos = _full_box(f, start)
    f.seek(pos)
    sizes = f.read(2)
    offset_size, length_size = sizes[0] >> 4, sizes[0] & 15
    base_size, index_size = sizes[1] >> 4, (sizes[1] & 15 if version else 0)
    for _ in range(_read_uint(f, 2 if version < 2 else 4)):
        item_id = _read_uint(f, 2 if version < 2 else 4)
        if version:
            f.read(2)  # construction method
        f.read(2)      # data reference index
        base = _read_uint(f, base_size)
        extents = [(_read_uint(f, index_size), _read_uint(f, offset_size), _read_uint(f, length_size))
                   for _ in range(_read_uint(f, 2))]
        if item_id == item and extents:
            return base + extents[0][1], extents[0][2]
    return None


def read_heic_date(path):
    try:
        with open(path, "rb") as f:
            end = f.seek(0, os.SEEK_END)
            for kind, payload, box_end in list(_boxes(f, 0, end)):
                if kind != b"meta":
                    continue
                children = {k: (p, e) for k, p, e in _boxes(f, payload + 4, box_end)}
                if b"iinf" not in children or b"iloc" not in children:
                    return None
                item = _heic_exif_item(f, *children[b"iinf"])
                location = item is not None and _heic_item_location(f, children[b"iloc"][0], item)
                if not location:
                    return None
                f.seek(location[0])
                data = f.read(location[1])
                tiff = data[4 + int.from_bytes(data[:4], "big"):]
                return _exif_date(piexif.load(tiff))
    except Exception:
        pass
    return None


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
    if ext in HEIC_EXTS:
        return read_heic_date(path)
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
        if nd and nd.kind == UTC_TIME and plan.embedded and _agrees(plan.embedded, nd):
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
        embedded = read_embedded_date(path)
        if name_date or embedded:
            plans.append(Plan(path, name_date, embedded))
        else:
            skipped.append(path)
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

    if nd is None:
        # Cameras (DSC_1234.JPG, GX010123.MP4) don't put the date in the name,
        # but do store it inside the file.
        plan.target = embedded
        plan.status = "Kept date inside file (no date in name)"
    elif embedded and _agrees(embedded, nd):
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


def _unique_name(name, used):
    stem, ext = os.path.splitext(name)
    n = 2
    while name.lower() in used:
        name = f"{stem} ({n}){ext}"
        n += 1
    used.add(name.lower())
    return name


def plan_new_paths(plans, root, add_prefix=False, month_folders=False):
    """Work out where each file should end up for the two optional tidy-ups.

    add_prefix: the name becomes "YYYY_MM_DD_####_<original name>", where
    #### counts from 0000 for the oldest file of each month in each folder.
    A prefix we added before is replaced, so running again with nothing new
    changes nothing.

    month_folders: files move into "<root>/YYYY_MM/". Files with the same
    name from different folders get " (2)" added rather than overwriting.
    """
    groups = {}
    for plan in plans:
        plan.new_path = None
        if plan.target and (add_prefix or month_folders):
            if month_folders:
                folder = os.path.join(root, f"{plan.target:%Y_%m}")
            else:
                folder = os.path.dirname(plan.path)
            key = (os.path.normcase(folder), plan.target.year, plan.target.month)
            groups.setdefault(key, (folder, []))[1].append(plan)

    for folder, group in groups.values():
        def base_name(p):
            name = os.path.basename(p.path)
            return PREFIX.sub("", name) if add_prefix else name
        def already_here(p):
            return os.path.normcase(os.path.dirname(p.path)) == os.path.normcase(folder)
        if add_prefix:
            group.sort(key=lambda p: (p.target, base_name(p).lower()))
        else:
            # Without numbers, files already in the folder keep their name and
            # newcomers with the same name get the " (2)".
            group.sort(key=lambda p: (not already_here(p), p.target, base_name(p).lower()))
        used = set()
        for number, plan in enumerate(group):
            name = base_name(plan)
            if add_prefix:
                name = f"{plan.target:%Y_%m_%d}_{number:04d}_{name}"
            path = os.path.join(folder, _unique_name(name, used))
            if os.path.normcase(path) != os.path.normcase(plan.path):
                plan.new_path = path


def plan_renumber(folder, recurse=True):
    """Close the gaps in #### left after deleting files.

    Only files that already have our prefix are touched, and they keep their
    order: within each month in each folder they become 0000, 0001, ...
    Dates aren't read, so this is quick. Apply the result with apply_plans().
    """
    groups = {}
    for path in find_media(folder, recurse):
        match = PREFIX.match(os.path.basename(path))
        if match:
            key = (os.path.normcase(os.path.dirname(path)), match["y"], match["m"])
            groups.setdefault(key, []).append((match["d"], match["n"], os.path.basename(path).lower(), path))

    plans = []
    for group in groups.values():
        for number, (_, _, _, path) in enumerate(sorted(group)):
            name = os.path.basename(path)
            match = PREFIX.match(name)
            wanted = f"{match['y']}_{match['m']}_{match['d']}_{number:04d}_{name[match.end():]}"
            plan = Plan(path, None, None)
            if wanted != name:
                plan.new_path = os.path.join(os.path.dirname(path), wanted)
            plans.append(plan)
    return plans


def apply_plan(plan):
    """Fix the dates of one file. Records any error on the plan."""
    if not plan.fixes_date:
        return
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


def _add_error(plan, message):
    plan.error = f"{plan.error}; {message}" if plan.error else message


def apply_plans(plans, root=None, progress=None):
    """Fix dates, then rename and move, for every plan that needs a change.

    When files are renumbered, one file's new name can be another's current
    name (0001 becoming 0000 while 0000 becomes 0001). Like swapping two
    parked cars, one has to be moved out of the way first, so every file being
    renamed gets a temporary name before its final one.
    """
    changes = [p for p in plans if p.needs_change]
    for i, p in enumerate(changes, 1):
        apply_plan(p)
        if progress:
            progress(i, len(changes))

    moving = []  # (plan, original path, temporary path)
    for n, p in enumerate(p for p in changes if p.new_path):
        temp = os.path.join(os.path.dirname(p.path), f"~renaming{n}~{os.path.basename(p.new_path)}")
        try:
            os.rename(p.path, temp)
            moving.append((p, p.path, temp))
        except OSError as exc:
            _add_error(p, f"Could not rename ({exc})")
    for p, original, temp in moving:
        try:
            if os.path.exists(p.new_path):
                raise FileExistsError(f"{os.path.basename(p.new_path)} already exists")
            os.makedirs(os.path.dirname(p.new_path), exist_ok=True)
            os.rename(temp, p.new_path)
            p.path = p.new_path
        except OSError as exc:
            _add_error(p, f"Could not rename or move ({exc})")
            try:
                os.rename(temp, original)
            except OSError:
                p.path = temp

    if root:
        _remove_emptied_folders({os.path.dirname(original) for _, original, _ in moving}, root)
    return changes


def _remove_emptied_folders(folders, root):
    """Remove folders (and their parents, up to root) that moving left empty."""
    root = os.path.normcase(os.path.abspath(root))
    for folder in sorted(folders, key=len, reverse=True):
        folder = os.path.abspath(folder)
        while os.path.normcase(folder) != root and os.path.normcase(folder).startswith(root + os.sep):
            try:
                os.rmdir(folder)  # only succeeds if the folder is empty
            except OSError:
                break
            folder = os.path.dirname(folder)


def write_log(plans, log_path):
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["File", "Date in name", "Date inside file before", "New date", "Result",
                         "Renamed or moved to", "Error"])
        for p in plans:
            writer.writerow([
                p.path,
                p.name_date.when.strftime("%d/%m/%Y %H:%M:%S") + f" ({p.name_date.kind})" if p.name_date else "",
                p.embedded.strftime("%d/%m/%Y %H:%M:%S") if p.embedded else "",
                p.target.strftime("%d/%m/%Y %H:%M:%S") if p.target else "",
                p.status,
                p.new_path or "",
                p.error,
            ])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fix photo/video dates from their file names.")
    parser.add_argument("folder")
    parser.add_argument("--apply", action="store_true", help="make the changes (default is preview only)")
    parser.add_argument("--no-recurse", action="store_true", help="ignore subfolders")
    parser.add_argument("--rename", action="store_true",
                        help="add YYYY_MM_DD_####_ to the start of each file name")
    parser.add_argument("--month-folders", action="store_true",
                        help="move files into YYYY_MM folders inside the folder")
    args = parser.parse_args(argv)

    plans, skipped = plan_folder(args.folder, recurse=not args.no_recurse)
    plan_new_paths(plans, args.folder, args.rename, args.month_folders)
    changes = [p for p in plans if p.needs_change]
    for p in changes:
        rename = f"  -> {os.path.relpath(p.new_path, args.folder)}" if p.new_path else ""
        print(f"{os.path.relpath(p.path, args.folder):45} {p.target:%d/%m/%Y %H:%M:%S}  {p.status}{rename}")
    print(f"\n{len(plans) - len(changes)} need no change, {len(changes)} to change, "
          f"{len(skipped)} with no date found.")

    if args.apply:
        for p in apply_plans(plans, args.folder):
            if p.error:
                print(f"{p.path}: {p.error}", file=sys.stderr)
        print("Done.")
    elif changes:
        print("Preview only. Run again with --apply to make the changes.")


if __name__ == "__main__":
    main()
