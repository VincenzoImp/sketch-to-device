---
name: device-app-development
description: Develop a request-specific app with the mounted device SDK, inspect relevant API documentation, exercise interactions, and export a checked artifact.
---

# Device app development

1. Read `/workspace/agent-sdk/INDEX.md` and the generated `/workspace/agent-sdk/manifest.json`. The manifest describes source APIs; it does not attest the device's installed firmware.
2. Understand the complete text/transcript/visual request. Read `/workspace/authoring.txt`, then only the API topics or source ranges needed to implement it. Reuse and combine primitives freely; examples do not limit application categories.
3. Write the request-specific AppSpec or documented unsupported result to `/workspace/out/app.json`. Use raw JSON and a quoted heredoc; never embed JSON as a Python dictionary literal.
4. Exercise the intended workflow and review the result against the input. Consult executable SDK scenarios and the reference runtime as needed. Tests authored by you are useful checks, not independent proof of intent fidelity.
5. Run `python3 /workspace/trusted_check.py`; fix concrete errors while budget remains. Preserve the canonical sources. Finish after its actual `VALIDATED_APP` or `UNSUPPORTED_REQUEST` hash marker.

Use short targeted reads/searches instead of full schema/source dumps. No package installation, shell networking, provider credentials or firmware flashing is available inside this job. Public research may use only the enabled managed tools, following `/workspace/agent-sdk/tools-and-assets.md`. This SDK currently exposes the implemented AppSpec runtime; it does not pretend that arbitrary script/native application execution is already available.
