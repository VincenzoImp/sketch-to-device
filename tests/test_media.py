"""Real image decoding and HTTP/JavaScript input bounds; no provider calls."""

import io
import base64
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from backend import media, media_limits, server

ROOT = Path(__file__).resolve().parent.parent


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    compressor = zlib.compressobj()
    row = b"\0" + bytes((x % 256 for x in range(width * 3)))
    compressed = b"".join(compressor.compress(row) for _ in range(height)) + compressor.flush()
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", compressed) + chunk(b"IEND", b""))


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
        if not Path(self.ffmpeg).exists():
            self.skipTest("Installed FFmpeg is required for the real decoder tests.")

    def normalize(self, raw, mime="image/png"):
        return media.normalize_photo(raw, mime, time.monotonic() + 20)

    def test_actual_high_resolution_photo_is_resized_and_small_photo_is_not_upscaled(self):
        for width, height in ((8000, 5000), (4000, 3000), (160, 80)):
            with self.subTest(width=width):
                normalized = self.normalize(png(width, height))
                expected = {8000: (2048, 1280), 4000: (2048, 1536), 160: (160, 80)}[width]
                self.assertEqual(media.photo_dimensions(normalized, "image/jpeg"), expected)
                self.assertLessEqual(len(normalized), media_limits.MAX_NORMALIZED_PHOTO_BYTES)

    def test_actual_webp_is_decoded_to_jpeg(self):
        raw = base64.b64decode("UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AAAAAA")
        normalized = self.normalize(raw, "image/webp")
        self.assertEqual(media.photo_dimensions(normalized, "image/jpeg"), (1, 1))

    def test_transparent_sketch_retains_black_strokes_on_white(self):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        # Transparent, opaque black, and half-transparent black bands.
        row = b"\0" + b"\0\0\0\0" * 16 + b"\0\0\0\xff" * 16 + b"\0\0\0\x80" * 16
        raw = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", 48, 16, 8, 6, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(row * 16)) + chunk(b"IEND", b""))
        normalized = self.normalize(raw)
        decoded = subprocess.run([self.ffmpeg, "-v", "error", "-i", "pipe:0", "-f", "rawvideo",
                                  "-pix_fmt", "rgb24", "pipe:1"], input=normalized,
                                 capture_output=True, timeout=10, check=True).stdout
        self.assertEqual(len(decoded), 48 * 16 * 3)
        for column, minimum, maximum in ((8, 245, 255), (24, 0, 10), (40, 117, 137)):
            self.assertTrue(all(minimum <= value <= maximum for value in decoded[column * 3:column * 3 + 3]))

    def test_actual_jpeg_exif_orientation_and_metadata_removal(self):
        raw = self.normalize(png(160, 80))
        exif = (b"Exif\0\0II" + struct.pack("<HIH", 42, 8, 1)
                + struct.pack("<HHI", 274, 3, 1) + struct.pack("<H", 6) + b"\0" * 6)
        marker = b"synthetic-private-location-marker"
        raw = (raw[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif
               + b"\xff\xfe" + struct.pack(">H", len(marker) + 2) + marker + raw[2:])
        result = self.normalize(raw, "image/jpeg")
        self.assertEqual(media.photo_dimensions(result, "image/jpeg"), (80, 160))
        self.assertNotIn(marker, result)
        self.assertNotIn(b"Exif\0\0", result)

    def test_overpixel_or_overdimension_headers_rejected_before_decoder(self):
        for width, height in ((8001, 5000), (12001, 1), (0, 20)):
            raw = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", width, height)
            with patch.object(media.subprocess, "run") as run:
                with self.assertRaises(media.MediaError) as caught:
                    self.normalize(raw)
                self.assertEqual(caught.exception.code, "media_dimensions")
                run.assert_not_called()

    def test_empty_corrupt_and_truncated_images_are_rejected(self):
        samples = [(b"", "image/png"), (png(16, 16)[:30], "image/png"),
                   (b"\xff\xd8\xff", "image/jpeg"), (b"not a picture", "image/webp")]
        for raw, mime in samples:
            with self.subTest(mime=mime, size=len(raw)), self.assertRaises(media.MediaError):
                self.normalize(raw, mime)

    def test_fixed_demuxer_protocol_pixel_and_time_bounds(self):
        actual_run = media.subprocess.run
        with patch.object(media.subprocess, "run", wraps=actual_run) as run:
            self.normalize(png(8, 4))
        argv = run.call_args.args[0]
        for flag, expected in (("-protocol_whitelist", "file,pipe"), ("-f", "png_pipe"),
                               ("-max_pixels", "40000000"), ("-frames:v", "1")):
            self.assertEqual(argv[argv.index(flag) + 1], expected)
        self.assertLessEqual(run.call_args.kwargs["timeout"], 20)
        with patch.object(media.subprocess, "run", side_effect=subprocess.TimeoutExpired("synthetic", 1)):
            with self.assertRaises(media.MediaError) as caught:
                self.normalize(png(8, 4))
            self.assertEqual(caught.exception.code, "media_timeout")

    def test_decoder_output_limit_is_enforced(self):
        def oversized(argv, **kwargs):
            Path(argv[-1]).write_bytes(b"x" * (media_limits.MAX_NORMALIZED_PHOTO_BYTES + 1))
            return SimpleNamespace(returncode=0)
        with patch.object(media.subprocess, "run", side_effect=oversized):
            with self.assertRaises(media.MediaError) as caught:
                self.normalize(png(8, 4))
            self.assertEqual(caught.exception.code, "media_size")

    def test_upload_bytes_and_total_limit_with_real_service(self):
        with tempfile.TemporaryDirectory() as directory:
            app = server.Application(Path(directory), generator=lambda *_: b"unused")
            first = app.upload("image/jpeg", b"x" * media_limits.MAX_UPLOAD_BYTES)["upload_id"]
            second = app.upload("image/jpeg", b"y" * (12 * 1024 * 1024 + 1))["upload_id"]
            with self.assertRaises(server.RequestError) as caught:
                app.generate({"prompt": "synthetic", "uploads": [first, second], "request_id": "a" * 32})
            self.assertEqual(caught.exception.code, "combined_media_too_large")
            self.assertFalse(app.busy)
            with self.assertRaises(server.RequestError):
                app.upload("image/jpeg", b"x" * (media_limits.MAX_UPLOAD_BYTES + 1))

    def test_http_413_rejects_before_reading_body(self):
        handler = object.__new__(server.Handler)
        handler.headers = {"Content-Length": str(media_limits.MAX_UPLOAD_BYTES + 1)}
        handler.rfile = io.BytesIO(b"unread")
        handler.connection = SimpleNamespace(settimeout=lambda _: None)
        with self.assertRaises(server.RequestError) as caught:
            handler.read_body(server.MAX_UPLOAD)
        self.assertEqual((caught.exception.code, caught.exception.status), ("invalid_body_size", 413))
        self.assertEqual(handler.rfile.tell(), 0)
        handler.headers = {"Content-Length": "5"}
        def timeout(_):
            raise TimeoutError("synthetic timeout")
        handler.rfile = SimpleNamespace(read=timeout)
        with self.assertRaises(server.RequestError) as caught:
            handler.read_body(server.MAX_UPLOAD)
        self.assertEqual((caught.exception.code, caught.exception.status), ("upload_timeout", 408))

    def test_actual_browser_logic_rejects_limits_and_stops_at_sixty_seconds(self):
        node = shutil.which("node") or "/opt/homebrew/bin/node"
        if not Path(node).exists():
            self.skipTest("Node is required for the actual browser logic check.")
        harness = r'''
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const elements=new Map(), events={};
function element(){return {hidden:true, children:[], classList:{toggle(){}},addEventListener(){},replaceChildren(){},append(){},textContent:''};}
const context={console, URLSearchParams,location:{hash:'',pathname:'/'},history:{replaceState(){}},
 sessionStorage:{getItem(){return null},setItem(){},removeItem(){}},document:{querySelector(s){if(!elements.has(s))elements.set(s,element());return elements.get(s)},createElement:element},
 navigator:{mediaDevices:{async getUserMedia(){return {getTracks(){return [{stop(){}}]}}}}},
 setTimeout(fn,ms){events.delay=ms; return 1},setInterval(){},clearTimeout(){}, File:class {},
 MediaRecorder:class {static isTypeSupported(){return true} constructor(){this.state='inactive'} start(){this.state='recording'} stop(){this.state='inactive'}}};
context.window=context; vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
vm.runInContext("addFiles([{name:'accepted',size:20*1024*1024},{name:'too-much-total',size:12*1024*1024+1}]); if(attachments.length!==1)throw Error('total limit');",context);
vm.runInContext("attachments=[]; addFiles([{name:'oversize',size:20*1024*1024+1},{name:'empty',size:0}]); if(attachments.length)throw Error('file limit');",context);
vm.runInContext("addFiles(Array.from({length:4},()=>({name:'small',size:1})));if(attachments.length!==3)throw Error('count limit'); attachments=[];",context);
vm.runInContext("if(!errors.invalid_body_size.includes('20 MiB') || !errors.media_duration.includes('60'))throw Error('media limit copy');",context);
(async()=>{await elements.get('#record').onclick();assert.equal(events.delay,60000);console.log('browser media checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run([node, "-e", harness, str(ROOT / "companion/app.js")],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("browser media checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
