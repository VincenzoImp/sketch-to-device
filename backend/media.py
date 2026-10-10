"""Bounded photo decoding using the existing local FFmpeg installation."""

import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time

from backend.media_limits import (MAX_NORMALIZED_PHOTO_BYTES, MAX_PHOTO_EDGE,
                                 MAX_PHOTO_PIXELS, MAX_PHOTO_SIDE,
                                 MAX_UPLOAD_BYTES, PHOTO_PROCESS_SECONDS)


class MediaError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def photo_dimensions(raw, mime):
    """Read image headers before a decoder can allocate a full pixel buffer."""
    try:
        if mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
            if raw[8:16] != b"\x00\x00\x00\rIHDR":
                raise MediaError("media")
            width, height = struct.unpack(">II", raw[16:24])
        elif mime == "image/jpeg" and raw.startswith(b"\xff\xd8"):
            offset = 2
            while offset < len(raw):
                if raw[offset] != 255:
                    raise MediaError("media")
                while offset < len(raw) and raw[offset] == 255:
                    offset += 1
                marker = raw[offset]
                offset += 1
                if marker in (0, 0xDA, 0xD9):
                    raise MediaError("media")
                if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                    continue
                size = int.from_bytes(raw[offset:offset + 2], "big")
                if size < 2 or offset + size > len(raw):
                    raise MediaError("media")
                if marker in (0xC0, 0xC1, 0xC2):
                    if size < 8:
                        raise MediaError("media")
                    height, width = struct.unpack(">HH", raw[offset + 3:offset + 7])
                    break
                offset += size
            else:
                raise MediaError("media")
        elif mime == "image/webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
            if len(raw) < 30 or int.from_bytes(raw[4:8], "little") + 8 != len(raw):
                raise MediaError("media")
            kind, size, body = raw[12:16], int.from_bytes(raw[16:20], "little"), raw[20:]
            if size > len(body):
                raise MediaError("media")
            if kind == b"VP8X" and size == 10:
                if body[0] & 2:  # Animated WebP is not a photo.
                    raise MediaError("media")
                width = 1 + int.from_bytes(body[4:7], "little")
                height = 1 + int.from_bytes(body[7:10], "little")
            elif kind == b"VP8 " and size >= 10 and body[3:6] == b"\x9d\x01\x2a":
                width = int.from_bytes(body[6:8], "little") & 0x3FFF
                height = int.from_bytes(body[8:10], "little") & 0x3FFF
            elif kind == b"VP8L" and size >= 5 and body[0] == 0x2F:
                bits = int.from_bytes(body[1:5], "little")
                width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            else:
                raise MediaError("media")
        else:
            raise MediaError("media")
    except (IndexError, struct.error):
        raise MediaError("media") from None
    if not (0 < width <= MAX_PHOTO_SIDE and 0 < height <= MAX_PHOTO_SIDE
            and width * height <= MAX_PHOTO_PIXELS):
        raise MediaError("media_dimensions")
    return width, height


def normalize_photo(raw, mime, deadline):
    """Return one oriented JPEG on white, with metadata removed and no upscaling."""
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise MediaError("media_size")
    photo_dimensions(raw, mime)
    ffmpeg = shutil.which("ffmpeg")
    fallback = "/opt/homebrew/bin/ffmpeg"
    if not ffmpeg and os.path.isfile(fallback) and os.access(fallback, os.X_OK):
        ffmpeg = fallback
    if not ffmpeg:
        raise MediaError("media_tools")
    timeout = min(PHOTO_PROCESS_SECONDS, deadline - time.monotonic())
    if timeout <= 0:
        raise MediaError("media_timeout")
    with tempfile.TemporaryDirectory(prefix="app-photo-") as directory:
        source, target = Path(directory) / "input", Path(directory) / "photo.jpg"
        source.write_bytes(raw)
        demuxer = {"image/jpeg": "jpeg_pipe", "image/png": "png_pipe", "image/webp": "webp_pipe"}[mime]
        scale = "scale=w='min({0},iw)':h='min({0},ih)':force_original_aspect_ratio=decrease".format(MAX_PHOTO_EDGE)
        # JPEG has no alpha channel. Composite transparent drawings over white
        # so black strokes remain readable instead of becoming a black image.
        filters = (scale + ",format=rgba,split[foreground][base];"
                   "[base]lutrgb=r=255:g=255:b=255,format=rgb24[background];"
                   "[background][foreground]overlay=shortest=1:format=auto")
        argv = [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-threads", "1", "-protocol_whitelist", "file,pipe",
                "-f", demuxer, "-max_pixels", str(MAX_PHOTO_PIXELS), "-i", str(source), "-frames:v", "1", "-vf", filters,
                "-map_metadata", "-1", "-pix_fmt", "yuvj420p", "-q:v", "8", "-threads", "1", str(target)]
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False)
            if result.returncode != 0:
                raise MediaError("media")
            with target.open("rb") as stream:
                image = stream.read(MAX_NORMALIZED_PHOTO_BYTES + 1)
        except subprocess.TimeoutExpired:
            raise MediaError("media_timeout") from None
        except OSError:
            raise MediaError("media") from None
    if not image or len(image) > MAX_NORMALIZED_PHOTO_BYTES:
        raise MediaError("media_size")
    width, height = photo_dimensions(image, "image/jpeg")
    if max(width, height) > MAX_PHOTO_EDGE:
        raise MediaError("media_dimensions")
    return image
