"""Real FFmpeg conversions verify source pixels, transparency and ownership seam."""

import hashlib
from pathlib import Path
import shutil
import struct
import time
import unittest
from unittest.mock import patch
import zlib

from backend import program_assets
from backend.media import MediaError, normalize_photo
from runtime.program import asset_bytes


def png(width, height, pixels):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    data = b"".join(b"\0" + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(data)) + chunk(b"IEND", b""))


class ProgramAssetTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("ffmpeg") and not Path("/opt/homebrew/bin/ffmpeg").exists():
            self.skipTest("Real FFmpeg is required")

    def convert(self, raw, width, height, **kwargs):
        return program_assets.convert_asset(raw, kwargs.pop("mime", "image/png"),
                                            asset_id="upload", width=width, height=height,
                                            deadline=time.monotonic() + 20, **kwargs)

    def test_transparent_and_partial_alpha_original_pixels_survive(self):
        pixels = b"\xff\0\0\x80\0\xff\0\0\0\0\xff\xff\xff\xff\xff\xff"
        raw = png(2, 2, pixels)
        result, provenance = self.convert(raw, 2, 2)
        self.assertEqual(asset_bytes(result), pixels)
        self.assertEqual(provenance["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(provenance["asset_sha256"], hashlib.sha256(pixels).hexdigest())
        self.assertNotEqual(raw[:8], asset_bytes(result)[:8])

    def test_contain_preserves_subject_and_adds_transparent_padding(self):
        result, _ = self.convert(png(4, 2, b"\xff\0\0\xff" * 8), 4, 4)
        pixels = asset_bytes(result)
        self.assertEqual(pixels[3:16:4], b"\0" * 4)
        self.assertEqual(pixels[16:48], b"\xff\0\0\xff" * 8)
        self.assertEqual(pixels[51:64:4], b"\0" * 4)

    def test_crop_uses_original_selected_subject(self):
        raw = png(4, 2, (b"\xff\0\0\xff" * 2 + b"\0\xff\0\x80" * 2) * 2)
        result, provenance = self.convert(raw, 2, 2, crop={"x": 5000, "y": 0, "width": 5000, "height": 10000})
        self.assertEqual(asset_bytes(result), b"\0\xff\0\x80" * 4)
        self.assertEqual(provenance["crop"]["x"], 5000)

    def test_cover_crop_has_requested_dimensions_without_padding(self):
        raw = png(8, 2, b"\0\0\xff\xff" * 16)
        result, _ = self.convert(raw, 2, 2, fit="cover")
        self.assertEqual(asset_bytes(result), b"\0\0\xff\xff" * 4)

    def test_exif_orientation_occurs_before_fit_and_metadata_removed(self):
        raw = normalize_photo(png(8, 4, b"\xff\0\0\xff" * 32), "image/png", time.monotonic() + 20)
        exif = (b"Exif\0\0II" + struct.pack("<HIH", 42, 8, 1)
                + struct.pack("<HHI", 274, 3, 1) + struct.pack("<H", 6) + b"\0" * 6)
        raw = raw[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + raw[2:]
        result, _ = self.convert(raw, 4, 8, mime="image/jpeg")
        self.assertEqual(asset_bytes(result)[3::4], b"\xff" * 32)
        self.assertNotIn(b"Exif", asset_bytes(result))

    def test_invalid_arguments_and_oversized_pixels_never_start_decoder(self):
        raw = png(2, 2, b"\0" * 16)
        for kwargs in ({"width": 320, "height": 432}, {"width": True, "height": 2},
                       {"width": 2, "height": 2, "crop": {"x": -1, "y": 0, "width": 1, "height": 1}},
                       {"width": 2, "height": 2, "fit": "cover;movie=https://example.test"}):
            with self.subTest(kwargs=kwargs), patch.object(program_assets.subprocess, "run") as run:
                with self.assertRaises(MediaError):
                    self.convert(raw, **kwargs)
                run.assert_not_called()

    def test_actual_conversion_is_deterministic(self):
        raw = png(3, 2, b"\x21\x85\xf7\x99" * 6)
        a, pa = self.convert(raw, 6, 4)
        b, pb = self.convert(raw, 6, 4)
        self.assertEqual((a, pa), (b, pb))

    def test_extreme_aspect_ratios_have_bounded_intermediate_and_nonzero_output(self):
        for width, height in ((12000, 1), (1, 12000)):
            for fit in ("cover", "contain"):
                raw = png(width, height, b"\x21\x85\xf7\xff" * (width * height))
                actual_run = program_assets.subprocess.run
                with self.subTest(dimensions=(width, height), fit=fit):
                    with patch.object(program_assets.subprocess, "run", wraps=actual_run) as run:
                        result, _ = self.convert(raw, 28, 432, fit=fit)
                    decoded = asset_bytes(result)
                    self.assertEqual(len(decoded), 28 * 432 * 4)
                    self.assertIn(255, decoded[3::4])
                    if fit == "cover":
                        self.assertEqual(decoded[3::4], b"\xff" * (28 * 432))
                        argv = run.call_args.args[0]
                        filters = argv[argv.index("-vf") + 1]
                        self.assertLess(filters.index("crop="), filters.index("scale="))


if __name__ == "__main__":
    unittest.main()
