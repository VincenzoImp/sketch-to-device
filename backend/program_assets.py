"""Prepare immutable device pixels from a job-owned original image.

The caller resolves ownership and passes bytes, never a model-supplied path or
URL. This conversion does not replace the separate perception JPEG pipeline.
"""

import base64
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from backend.media import MediaError, photo_dimensions
from backend.media_limits import MAX_PHOTO_PIXELS, MAX_UPLOAD_BYTES, PHOTO_PROCESS_SECONDS
from runtime.program import IDENTIFIER, LIMITS, PROFILE, asset_bytes


def convert_asset(raw, mime, *, asset_id, width, height, deadline, fit="contain", crop=None):
    """Orient, optionally crop, resize and preserve alpha in canonical RGBA.

    Crop uses integer ten-thousandths of the oriented image: x,y,width,height.
    Contain adds transparent padding; cover fills and center-crops the result.
    Returned provenance belongs in private job storage, not in the app package.
    """
    if (type(raw) is not bytes or not raw or len(raw) > MAX_UPLOAD_BYTES
            or type(asset_id) is not str or not IDENTIFIER.fullmatch(asset_id)
            or type(width) is not int or type(height) is not int
            or not 1 <= width <= PROFILE["viewport"]["width"]
            or not 1 <= height <= PROFILE["viewport"]["height"]
            or width * height * 4 > LIMITS["decoded_asset_bytes"]
            or type(fit) is not str or fit not in {"contain", "cover"}):
        raise MediaError("asset_arguments")
    original_width, original_height = photo_dimensions(raw, mime)
    if crop is not None:
        if (type(crop) is not dict or set(crop) != {"x", "y", "width", "height"}
                or any(type(value) is not int for value in crop.values())
                or not 0 <= crop["x"] < 10000 or not 0 <= crop["y"] < 10000
                or not 1 <= crop["width"] <= 10000 - crop["x"]
                or not 1 <= crop["height"] <= 10000 - crop["y"]):
            raise MediaError("asset_crop")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg and os.access("/opt/homebrew/bin/ffmpeg", os.X_OK):
        ffmpeg = "/opt/homebrew/bin/ffmpeg"
    if not ffmpeg:
        raise MediaError("media_tools")
    timeout = min(PHOTO_PROCESS_SECONDS, deadline - time.monotonic())
    if timeout <= 0:
        raise MediaError("media_timeout")
    filters = ["format=rgba"]
    if crop is not None:
        # Integers only, after automatic EXIF orientation, no filter expressions
        # are accepted from the caller.
        filters.append("crop=w=iw*{width}/10000:h=ih*{height}/10000:x=iw*{x}/10000:y=ih*{y}/10000".format(**crop))
    if fit == "contain":
        filters.extend([("scale=w='max(1,trunc(iw*min({w}/iw,{h}/ih)))':"
                         "h='max(1,trunc(ih*min({w}/iw,{h}/ih)))':flags=lanczos").format(w=width, h=height),
                        "pad={}:{}:(ow-iw)/2:(oh-ih)/2:color=0x00000000".format(width, height)])
    else:
        # Crop BEFORE scaling: a very wide/tall source must not create a huge
        # intermediate image merely to discard most of it. Quantize a subpixel
        # crop to one source pixel; no filter buffer exceeds source/output bounds.
        filters.extend([("crop=w='max(1,min(iw,ih*{w}/{h}))':"
                         "h='max(1,min(ih,iw*{h}/{w}))':x=(iw-ow)/2:y=(ih-oh)/2").format(w=width, h=height),
                        "scale={}:{}:flags=lanczos".format(width, height)])
    filters.append("format=rgba")
    with tempfile.TemporaryDirectory(prefix="device-asset-") as temporary:
        source, target = Path(temporary) / "original", Path(temporary) / "pixels.rgba"
        fd = os.open(str(source), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        demuxer = {"image/jpeg": "jpeg_pipe", "image/png": "png_pipe", "image/webp": "webp_pipe"}[mime]
        argv = [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-threads", "1",
                "-protocol_whitelist", "file,pipe", "-f", demuxer,
                "-max_pixels", str(MAX_PHOTO_PIXELS), "-i", str(source),
                "-frames:v", "1", "-vf", ",".join(filters), "-map_metadata", "-1",
                "-threads", "1", "-pix_fmt", "rgba", "-f", "rawvideo", str(target)]
        try:
            timeout = min(PHOTO_PROCESS_SECONDS, deadline - time.monotonic())
            if timeout <= 0:
                raise MediaError("media_timeout")
            completed = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=timeout, check=False,
                                       env={"PATH": "/usr/bin:/bin", "TMPDIR": temporary})
            if completed.returncode:
                raise MediaError("asset_decode")
            with target.open("rb") as stream:
                pixels = stream.read(width * height * 4 + 1)
        except subprocess.TimeoutExpired:
            raise MediaError("media_timeout") from None
        except OSError:
            raise MediaError("asset_decode") from None
    if len(pixels) != width * height * 4:
        raise MediaError("asset_decode")
    asset = {"id": asset_id, "width": width, "height": height, "format": "rgba8888",
             "sha256": hashlib.sha256(pixels).hexdigest(),
             "data_b64": base64.b64encode(pixels).decode("ascii")}
    asset_bytes(asset)
    provenance = {"source_sha256": hashlib.sha256(raw).hexdigest(), "source_mime_type": mime,
                  "source_header_dimensions": [original_width, original_height],
                  "orientation": "decoder_exif", "fit": fit, "crop": crop,
                  "output_dimensions": [width, height], "asset_sha256": asset["sha256"]}
    return asset, provenance
