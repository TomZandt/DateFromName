import os
import struct
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

import piexif
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import datefromname as core  # noqa: E402

DOWNLOADED = datetime(2026, 10, 31, 12, 21)


def make_jpeg(path, taken=None, trailer=b""):
    Image.new("RGB", (8, 8), "red").save(path, "JPEG")
    if taken:
        stamp = taken.strftime(core.EXIF_FORMAT).encode()
        piexif.insert(piexif.dump({"Exif": {piexif.ExifIFD.DateTimeOriginal: stamp}}), path)
    with open(path, "ab") as f:
        f.write(trailer)  # e.g. the video inside a Pixel motion photo
    core.set_file_times(path, DOWNLOADED)


def box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def make_mp4(path, created_utc=None):
    seconds = int((created_utc - core.QUICKTIME_EPOCH).total_seconds()) if created_utc else 0
    header = b"\x00\x00\x00\x00" + struct.pack(">II", seconds, seconds) + b"\x00" * 20
    moov = box(b"moov", box(b"mvhd", header) + box(b"trak", box(b"tkhd", header) +
                                                        box(b"mdia", box(b"mdhd", header))))
    with open(path, "wb") as f:
        f.write(box(b"ftyp", b"isom\x00\x00\x00\x00") + box(b"mdat", b"\x01" * 64) + moov)
    core.set_file_times(path, DOWNLOADED)


class ParseNameTests(unittest.TestCase):
    def test_patterns(self):
        cases = {
            "IMG-20260822-WA0004.jpeg": (datetime(2026, 8, 22), core.DATE_ONLY, 4),
            "VID-20260825-WA0029.mp4": (datetime(2026, 8, 25), core.DATE_ONLY, 29),
            "PXL_20260822_092200562.MP.jpg": (datetime(2026, 8, 22, 9, 22), core.UTC_TIME, 0),
            "IMG_20260822_123456.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "Screenshot_20260822-123456.png": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "WhatsApp Image 2026-08-22 at 9.05.01.jpeg": (datetime(2026, 8, 22, 9, 5, 1), core.LOCAL_TIME, 0),
            "holiday 2026-08-22 (2).jpg": (datetime(2026, 8, 22), core.DATE_ONLY, 0),
            "IMG-20260822-WA0004~2.jpg": (datetime(2026, 8, 22), core.DATE_ONLY, 4),
            "PXL_20260822_092200562.TS.mp4": (datetime(2026, 8, 22, 9, 22), core.UTC_TIME, 0),
            "WhatsApp Image 2026-08-22 at 9.05.01 PM.jpeg": (datetime(2026, 8, 22, 21, 5, 1), core.LOCAL_TIME, 0),
            "WhatsApp Video 2026-08-22 at 12.05.01 AM (1).mp4": (datetime(2026, 8, 22, 0, 5, 1), core.LOCAL_TIME, 0),
            "20260822_123456.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "20260822_123456(0).jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "IMG20260822123456.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "VID20260822123456.mp4": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "MVIMG_20260822_123456.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "IMG_20260822_123456_HDR.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "DJI_20260822123456_0001_D.JPG": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "Screenshot_2026-08-22-12-34-56-123_com.whatsapp.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "Screenshot 2026-08-22 123456.png": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "photo_2026-08-22_12-34-56.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "photo_123@22-08-2026_12-34-56.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "2026-08-22 12.34.56.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "signal-2026-08-22-123456.jpg": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "2026_0822_123456_001.MP4": (datetime(2026, 8, 22, 12, 34, 56), core.LOCAL_TIME, 0),
            "FB_IMG_1787398496123.jpg": (datetime(2026, 8, 22, 11, 34, 56), core.UTC_TIME, 0),
            "RPReplay_Final1787398496.MP4": (datetime(2026, 8, 22, 11, 34, 56), core.UTC_TIME, 0),
            "1787398496123.jpg": (datetime(2026, 8, 22, 11, 34, 56), core.UTC_TIME, 0),
        }
        for name, (when, kind, seq) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(core.parse_name(name), core.NameDate(when, kind, seq))

    def test_no_date(self):
        for name in ("DSC_1234.jpg", "IMG_99999999.jpg", "photo.jpg", "GX010123.MP4",
                     "IMG_1234.HEIC", "P1010123.JPG", "IMG_20261399_123456.jpg"):
            self.assertIsNone(core.parse_name(name))


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def run_fix(self):
        plans, skipped = core.plan_folder(self.dir)
        for p in plans:
            if p.needs_change:
                core.apply_plan(p)
                self.assertEqual(p.error, "")
        return {os.path.basename(p.path): p for p in plans}, skipped

    def modified(self, name):
        return datetime.fromtimestamp(os.path.getmtime(self.path(name)))

    def test_whatsapp_photos_get_date_and_keep_order(self):
        make_jpeg(self.path("IMG-20260822-WA0002.jpeg"))
        make_jpeg(self.path("IMG-20260822-WA0010.jpeg"))
        self.run_fix()
        first = core.read_jpeg_date(self.path("IMG-20260822-WA0002.jpeg"))
        second = core.read_jpeg_date(self.path("IMG-20260822-WA0010.jpeg"))
        self.assertEqual(first, datetime(2026, 8, 22, 12, 0, 2))
        self.assertLess(first, second)
        self.assertEqual(self.modified("IMG-20260822-WA0002.jpeg"), first)

    def test_correct_photo_untouched(self):
        taken = datetime(2026, 8, 22, 12, 24, 11)
        make_jpeg(self.path("PXL_20260822_092411373.MP.jpg"), taken)
        core.set_file_times(self.path("PXL_20260822_092411373.MP.jpg"), taken)
        plans, _ = core.plan_folder(self.dir)
        self.assertFalse(plans[0].needs_change)

    def test_correct_exif_but_download_file_date_is_synced(self):
        taken = datetime(2026, 8, 22, 12, 24, 11)
        make_jpeg(self.path("PXL_20260822_092411373.MP.jpg"), taken)
        plans, _ = self.run_fix()
        plan = plans["PXL_20260822_092411373.MP.jpg"]
        self.assertFalse(plan.write_embedded)
        self.assertEqual(self.modified("PXL_20260822_092411373.MP.jpg"), taken)

    def test_pixel_without_exif_uses_neighbours_time_zone(self):
        make_jpeg(self.path("PXL_20260822_092200562.MP.jpg"), datetime(2026, 8, 22, 12, 22, 0))  # UTC+3
        make_jpeg(self.path("PXL_20260822_092330450.jpg"), trailer=b"MOTION-VIDEO")
        self.run_fix()
        self.assertEqual(core.read_jpeg_date(self.path("PXL_20260822_092330450.jpg")),
                         datetime(2026, 8, 22, 12, 23, 30))
        with open(self.path("PXL_20260822_092330450.jpg"), "rb") as f:
            self.assertTrue(f.read().endswith(b"MOTION-VIDEO"))

    def test_older_date_inside_file_is_kept(self):
        taken = datetime(2025, 1, 5, 10, 0)
        make_jpeg(self.path("IMG-20260822-WA0001.jpeg"), taken)
        plans, _ = self.run_fix()
        self.assertFalse(plans["IMG-20260822-WA0001.jpeg"].write_embedded)
        self.assertEqual(core.read_jpeg_date(self.path("IMG-20260822-WA0001.jpeg")), taken)

    def test_later_date_inside_file_is_replaced(self):
        make_jpeg(self.path("IMG-20260822-WA0001.jpeg"), DOWNLOADED)
        self.run_fix()
        self.assertEqual(core.read_jpeg_date(self.path("IMG-20260822-WA0001.jpeg")).date(),
                         datetime(2026, 8, 22).date())

    def test_video_without_date(self):
        make_mp4(self.path("VID-20260825-WA0029.mp4"))
        self.run_fix()
        self.assertEqual(core.read_mp4_date(self.path("VID-20260825-WA0029.mp4")),
                         datetime(2026, 8, 25, 12, 0, 29))

    def test_video_keeps_real_time_from_file_date(self):
        make_mp4(self.path("VID-20260826-WA0003.mp4"))
        real = datetime(2026, 8, 26, 10, 11)
        core.set_file_times(self.path("VID-20260826-WA0003.mp4"), real)
        self.run_fix()
        self.assertEqual(core.read_mp4_date(self.path("VID-20260826-WA0003.mp4")), real)

    def test_video_already_correct(self):
        make_mp4(self.path("VID-20260901-WA0014.mp4"), core.local_to_utc(datetime(2026, 9, 1, 19, 51)))
        plans, _ = self.run_fix()
        plan = plans["VID-20260901-WA0014.mp4"]
        self.assertEqual(plan.status, "Already correct, file dates updated")
        self.assertFalse(plan.write_embedded)

    def test_files_without_dates_are_skipped(self):
        make_jpeg(self.path("photo.jpg"))
        with open(self.path("notes.txt"), "w") as f:
            f.write("hi")
        plans, skipped = core.plan_folder(self.dir)
        self.assertEqual(plans, [])
        self.assertEqual([os.path.basename(s) for s in skipped], ["photo.jpg"])

    def test_camera_names_use_date_inside_file(self):
        taken = datetime(2026, 8, 22, 15, 0, 0)
        make_jpeg(self.path("DSC_1234.JPG"), taken)
        make_mp4(self.path("GX010123.MP4"), core.local_to_utc(taken))
        plans, skipped = self.run_fix()
        self.assertEqual(skipped, [])
        for name in ("DSC_1234.JPG", "GX010123.MP4"):
            self.assertFalse(plans[name].write_embedded)
            self.assertEqual(self.modified(name), taken)

    def test_iphone_heic_uses_date_inside_file(self):
        try:
            import pillow_heif
        except ImportError:
            self.skipTest("pillow-heif not installed")
        pillow_heif.register_heif_opener()
        taken = datetime(2026, 8, 22, 15, 4, 5)
        stamp = taken.strftime(core.EXIF_FORMAT).encode()
        Image.new("RGB", (64, 64), "blue").save(
            self.path("IMG_1234.HEIC"), format="HEIF",
            exif=piexif.dump({"Exif": {piexif.ExifIFD.DateTimeOriginal: stamp}}))
        core.set_file_times(self.path("IMG_1234.HEIC"), DOWNLOADED)
        plans, skipped = self.run_fix()
        self.assertEqual(skipped, [])
        self.assertFalse(plans["IMG_1234.HEIC"].write_embedded)
        self.assertEqual(self.modified("IMG_1234.HEIC"), taken)

    def test_created_date_is_set(self):
        make_jpeg(self.path("IMG-20260822-WA0002.jpeg"))
        self.run_fix()
        created, _ = core.get_file_times(self.path("IMG-20260822-WA0002.jpeg"))
        self.assertEqual(created, datetime(2026, 8, 22, 12, 0, 2))


if __name__ == "__main__":
    unittest.main()
