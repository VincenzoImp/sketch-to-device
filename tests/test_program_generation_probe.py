"""Negative fidelity cases executed by the real shared native renderer."""

import base64
import contextlib
import hashlib
import io
import json
import time
import unittest
from unittest.mock import patch

from backend.program_runner import execute_program
from runtime.program import assemble_program
from scripts import probe_program_generation as probe


class GenerationProbeTests(unittest.TestCase):
    def package(self, *, draw="gfx.image('reference',20,100);", condition="e.type==='up'", name="Reference Switch"):
        rgb = probe.reference_rgb()
        rgba = b"".join(rgb[i:i + 3] + b"\xff" for i in range(0, len(rgb), 3))
        asset = dict(id="reference", width=24, height=24, format="rgba8888",
                     sha256=hashlib.sha256(rgba).hexdigest(), data_b64=base64.b64encode(rgba).decode())
        source = ("let i=0;const c=['#FF0000','#00FF00','#0000FF'];"
                  "function draw(){gfx.begin(c[i]);" + draw + "gfx.end();}"
                  "draw();app.onPointer(e=>{if(" + condition + "){i=(i+1)%3;draw();}});")
        return assemble_program(app_id="probe", name=name, version=1, source=source, assets=[asset],
                                requires=["canvas", "input", "time"])

    def run_package(self, body):
        return execute_program(body, probe.scenario(), deadline=time.monotonic() + 20)

    def test_full_frames_and_real_asset_dependence_pass(self):
        body = self.package()
        self.assertTrue(probe.verify_generated(body, self.run_package(body)))
        self.assertTrue(probe.check_asset_dependence(body))

    def test_wrong_title_spatial_fidelity_and_center_only_input_fail(self):
        for body in (self.package(name="Wrong"),
                     self.package(draw="gfx.image('reference',20,100);gfx.rect(0,0,10,10,'#000000');"),
                     self.package(condition="e.type==='up'&&e.x===160&&e.y===216")):
            self.assertFalse(probe.verify_generated(body, self.run_package(body)))

    def test_unused_matching_asset_cannot_prove_reuse(self):
        colors = ("#FFFF00", "#FF00FF", "#00FFFF", "#FFFFFF")
        draw = "".join("gfx.rect(%d,%d,6,6,'%s');" % (20+x*6,100+y*6,colors[(x+y)%4])
                       for y in range(4) for x in range(4))
        body = self.package(draw=draw)
        self.assertTrue(probe.verify_generated(body, self.run_package(body)))
        self.assertFalse(probe.check_asset_dependence(body))

    def test_default_does_not_start_provider_or_make_a_job(self):
        output = io.StringIO()
        with patch.object(probe, "run_program_agent") as provider, contextlib.redirect_stdout(output):
            self.assertEqual(probe.main([]), 0)
        provider.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {"status": "ready_for_live_probe", "device_installed": False})


if __name__ == "__main__":
    unittest.main()
