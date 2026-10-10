"""Package boundary tests use independently constructed wire bytes and pixels."""

import base64
import hashlib
import json
import unittest

from runtime.program import (LIMITS, assemble_program, asset_bytes, program_report,
                             validate_program)
from runtime.validation import ValidationError


def example():
    # General code with arithmetic and functions, not a prebuilt application.
    return {"schema_version": 2, "app_id": "probe", "name": "Package probe",
            "version": 7, "runtime": "quickjs-ng-0.14.0", "sdk": "device-js-1",
            "profile": "p4-canvas-1", "requires": ["canvas", "input", "time"],
            "source": "const twice = x => x * 2; let values = [1, 2].map(twice);",
            "assets": []}


def pixels(identifier="image"):
    raw = bytes([255, 0, 0, 128, 0, 255, 0, 0])
    return {"id": identifier, "width": 2, "height": 1, "format": "rgba8888",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "data_b64": base64.b64encode(raw).decode()}


def wire(app):
    return json.dumps(app, ensure_ascii=True, separators=(",", ":")).encode()


class ProgramPackageTests(unittest.TestCase):
    def reject(self, app, code):
        with self.assertRaises(ValidationError) as raised:
            validate_program(wire(app))
        self.assertEqual(raised.exception.code, code)

    def test_arbitrary_source_preserved_and_report_is_not_execution_proof(self):
        app = example()
        app["source"] += "\n// 😀 Unicode remains source, not a model instruction to the host."
        raw = wire(app)
        self.assertEqual(validate_program(raw), app)
        report = program_report(raw)
        self.assertEqual(report["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(report["execution_verified"])
        app["source"] = "function { invalid syntax"
        self.assertEqual(validate_program(wire(app))["source"], app["source"])

    def test_raw_rgba_alpha_and_order_are_exact(self):
        image = pixels()
        self.assertEqual(asset_bytes(image), b"\xff\0\0\x80\0\xff\0\0")
        app = example()
        app["assets"] = [image]
        self.assertEqual(program_report(wire(app))["decoded_asset_bytes"], 8)

    def test_tampered_pixel_hash_and_wrong_length_rejected(self):
        app = example()
        app["assets"] = [pixels()]
        app["assets"][0]["sha256"] = "0" * 64
        self.reject(app, "asset_hash")
        app["assets"][0] = pixels()
        app["assets"][0]["width"] = 3
        self.reject(app, "asset_bytes")

    def test_noncanonical_padding_and_whitespace_rejected(self):
        app = example()
        image = pixels()
        # Change unused padding bits: permissive decoders return identical bytes.
        self.assertTrue(image["data_b64"].endswith("AA="))
        image["data_b64"] = image["data_b64"][:-2] + "B="
        app["assets"] = [image]
        self.reject(app, "asset_encoding")
        image["data_b64"] = pixels()["data_b64"] + "\n"
        self.reject(app, "asset_bytes")

    def test_aggregate_decoded_budget_and_duplicate_assets(self):
        app = example()
        raw = b"\0" * (96 * 96 * 4)
        image = {"id": "large", "width": 96, "height": 96, "format": "rgba8888",
                 "sha256": hashlib.sha256(raw).hexdigest(), "data_b64": base64.b64encode(raw).decode()}
        app["assets"] = [pixels(), pixels()]
        self.reject(app, "asset_id")
        # A single 96px RGBA image fits the current package envelope.
        app["assets"] = [image]
        self.assertEqual(program_report(wire(app))["decoded_asset_bytes"], len(raw))
        app["assets"] *= 2
        self.reject(app, "bytes")

    def test_unknown_fields_capabilities_and_types_rejected(self):
        for key, value, code in (("version", True, "integer"), ("schema_version", 1, "integer"),
                                 ("version", 1.0, "number"), ("source", "", "bytes"),
                                 ("runtime", "node", "compatibility"),
                                 ("requires", ["camera"], "capability"),
                                 ("requires", ["input", "input"], "capability"),
                                 ("requires", [["input"]], "capability"),
                                 ("app_id", "../other", "identifier"), ("name", "x\0", "name")):
            with self.subTest(key=key, value=value):
                app = example()
                app[key] = value
                self.reject(app, code)
        app = example()
        app["receipt"] = "model-says-passed"
        self.reject(app, "fields")

    def test_duplicate_keys_nested_depth_and_non_json_numbers(self):
        for raw, code in ((wire(example())[:-1] + b',"version":8}', "duplicate_key"),
                          (b'[' * 13 + b'0' + b']' * 13, "depth"),
                          (b'{"version":NaN}', "number"), (b'\xff', "encoding"),
                          (b'{} trailing', "json")):
            with self.subTest(code=code), self.assertRaises(ValidationError) as raised:
                validate_program(raw)
            self.assertEqual(raised.exception.code, code)

    def test_nul_and_unpaired_surrogates_are_rejected(self):
        for source in ("\0", "\ud800", "ok\udfff"):
            app = example()
            app["source"] = source
            self.reject(app, "encoding")

    def test_exact_serialization_reserves_identity_before_execution(self):
        args = {k: v for k, v in example().items()
                if k in {"app_id", "name", "version", "source", "assets", "requires"}}
        first = assemble_program(**args)
        self.assertEqual(first, assemble_program(**args))
        self.assertEqual(validate_program(first)["version"], 7)
        args["version"] = 8
        self.assertNotEqual(program_report(first)["sha256"],
                            program_report(assemble_program(**args))["sha256"])

    def test_whole_envelope_exact_boundary(self):
        app = example()
        app["source"] = "x"
        remaining = LIMITS["package_bytes"] - len(wire(app))
        app["source"] += " " * remaining
        self.assertEqual(len(wire(app)), LIMITS["package_bytes"])
        validate_program(wire(app))
        app["source"] += " "
        self.reject(app, "bytes")


if __name__ == "__main__":
    unittest.main()
