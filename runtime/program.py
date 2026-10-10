"""Strict schema2 package checks; engine execution is a separate required step.

No source is executed here. A successful report proves bounded structure and
asset integrity, not syntax, behavior, current device capabilities or safety.
"""

import base64
import binascii
import hashlib
import json
from pathlib import Path
import re

from runtime.validation import ValidationError

PROFILE = json.loads((Path(__file__).resolve().parents[1] /
                      "contracts/program-profile.json").read_text())
LIMITS = PROFILE["limits"]
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z", re.ASCII)
DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
PACKAGE_FIELDS = {"schema_version", "app_id", "name", "version", "runtime", "sdk",
                  "profile", "requires", "source", "assets"}
ASSET_FIELDS = {"id", "width", "height", "format", "sha256", "data_b64"}


def fail(code, path, message):
    raise ValidationError(code, path, message)


def _object(value, fields, path):
    if type(value) is not dict:
        fail("type", path, "Expected an object")
    if set(value) != fields:
        fail("fields", path, "Object fields do not match the versioned contract")


def _integer(value, lower, upper, path):
    if type(value) is not int or not lower <= value <= upper:
        fail("integer", path, "Expected an integer within the resource profile")


def _identifier(value, path):
    if type(value) is not str or not IDENTIFIER.fullmatch(value):
        fail("identifier", path, "Expected a bounded lowercase ASCII identifier")


def _utf8(value, path, maximum):
    if type(value) is not str or "\0" in value:
        fail("encoding", path, "Expected text without NUL")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        fail("encoding", path, "Unpaired Unicode surrogate is not allowed")
    if not 1 <= len(encoded) <= maximum:
        fail("bytes", path, "Text exceeds the resource profile or is empty")
    return encoded


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            fail("duplicate_key", "$", "JSON contains a repeated key")
        result[key] = value
    return result


def _non_integer(_):
    fail("number", "$", "Only integer JSON metadata is allowed")


def decode(raw, *, maximum=LIMITS["package_bytes"]):
    """Parse bounded JSON before allocating its full object graph."""
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
        fail("bytes", "$", "Expected bounded nonempty package bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("encoding", "$", "JSON must use UTF-8")
    depth = 0
    quoted = escaped = False
    for char in text:
        if char == "\0":
            fail("encoding", "$", "NUL is not allowed")
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > LIMITS["json_depth"]:
                fail("depth", "$", "JSON exceeds the container-depth limit")
        elif char in "]}":
            depth -= 1
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_float=_non_integer, parse_constant=_non_integer)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, ValidationError):
            raise
        fail("json", "$", "Malformed JSON")


def asset_bytes(asset, path="$.assets[]"):
    """Validate the wire representation and return exact decoded RGBA bytes."""
    _object(asset, ASSET_FIELDS, path)
    _identifier(asset["id"], path + ".id")
    _integer(asset["width"], 1, PROFILE["viewport"]["width"], path + ".width")
    _integer(asset["height"], 1, PROFILE["viewport"]["height"], path + ".height")
    if asset["format"] != PROFILE["asset_format"]:
        fail("asset_format", path, "Unsupported asset pixel format")
    size = asset["width"] * asset["height"] * 4
    if size > LIMITS["decoded_asset_bytes"]:
        fail("asset_bytes", path, "Decoded asset exceeds the profile")
    encoded = asset["data_b64"]
    if type(encoded) is not str or len(encoded) != 4 * ((size + 2) // 3):
        fail("asset_bytes", path, "Encoded asset length does not match its dimensions")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        fail("asset_encoding", path, "Asset must use canonical base64")
    if len(raw) != size or base64.b64encode(raw).decode("ascii") != encoded:
        fail("asset_encoding", path, "Asset must use canonical base64")
    if (type(asset["sha256"]) is not str or not DIGEST.fullmatch(asset["sha256"])
            or hashlib.sha256(raw).hexdigest() != asset["sha256"]):
        fail("asset_hash", path, "Asset hash does not match its pixels")
    return raw


def validate_program(raw):
    """Validate against the implementation profile, not a device's live state."""
    app = decode(raw)
    _object(app, PACKAGE_FIELDS, "$")
    _integer(app["schema_version"], 2, 2, "$.schema_version")
    _identifier(app["app_id"], "$.app_id")
    _integer(app["version"], 1, 2147483647, "$.version")
    name = app["name"]
    if (type(name) is not str or not 1 <= len(name) <= 48
            or any(not 32 <= ord(char) <= 126 for char in name)):
        fail("name", "$.name", "Title must use 1..48 printable ASCII characters")
    for field, expected in (("runtime", PROFILE["engine"]), ("sdk", PROFILE["sdk"]),
                            ("profile", PROFILE["profile"])):
        if type(app[field]) is not str or app[field] != expected:
            fail("compatibility", "$." + field, "Unknown runtime, SDK or resource profile")
    modules = app["requires"]
    if (type(modules) is not list or len(modules) > len(PROFILE["modules"])
            or any(type(item) is not str or item not in PROFILE["modules"] for item in modules)
            or len(set(modules)) != len(modules)):
        fail("capability", "$.requires", "Required modules are unsupported or repeated")
    _utf8(app["source"], "$.source", LIMITS["source_bytes"])
    assets = app["assets"]
    if type(assets) is not list or len(assets) > LIMITS["asset_count"]:
        fail("asset_count", "$.assets", "Too many assets")
    seen, total = set(), 0
    for index, asset in enumerate(assets):
        path = "$.assets[{}]".format(index)
        total += len(asset_bytes(asset, path))
        if asset["id"] in seen:
            fail("asset_id", path, "Asset identifiers must be unique")
        seen.add(asset["id"])
        if total > LIMITS["decoded_asset_bytes"]:
            fail("asset_bytes", "$.assets", "Combined decoded assets exceed the profile")
    return app


def program_report(raw):
    app = validate_program(raw)
    return {"schema_version": 2, "app_id": app["app_id"], "name": app["name"],
            "version": app["version"], "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw), "source_sha256": hashlib.sha256(app["source"].encode()).hexdigest(),
            "runtime": app["runtime"], "sdk": app["sdk"], "profile": app["profile"],
            "min_runtime_version": PROFILE["runtime_version"], "requires": app["requires"],
            "asset_count": len(app["assets"]),
            "decoded_asset_bytes": sum(a["width"] * a["height"] * 4 for a in app["assets"]),
            "execution_verified": False}


def assemble_program(*, app_id, name, version, source, assets, requires):
    """Freeze exact bytes. Callers own version reservation and asset provenance."""
    app = {"schema_version": 2, "app_id": app_id, "name": name, "version": version,
           "runtime": PROFILE["engine"], "sdk": PROFILE["sdk"], "profile": PROFILE["profile"],
           "requires": requires, "source": source, "assets": assets}
    try:
        raw = json.dumps(app, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeEncodeError, RecursionError):
        fail("encoding", "$", "Package cannot be serialized as UTF-8 JSON")
    validate_program(raw)
    return raw
