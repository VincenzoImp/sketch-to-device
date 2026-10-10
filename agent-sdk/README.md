# Device application SDK

This is the consultable SDK for the implemented AppSpec interpreter. It is a foundation for a future programmable engine, not evidence that Lua, JavaScript or native application loading exists.

The generator mounts these public files into its remote environment. It also creates `manifest.json` from the exact canonical schema, capabilities and runtime source, including their hashes. No limits or API version should be inferred from an example.

Start at [the index](INDEX.md), then read the relevant API topic and examples. Examples demonstrate combinations of primitives; they do not define an allowed list of application categories.

The SDK's source capabilities and the physical device's installed firmware are separate. At the SDK's initial checkpoint, color support existed in runtime 0.2 source, while the last confirmed flashed runtime was 0.1. Do not infer a flash from a build or from this document. The generated manifest deliberately does not attest the device version; setup and device delivery checks own that evidence.

Google documents automatic startup loading at `.agents/AGENTS.md` and skill discovery at `.agents/skills/<name>/SKILL.md`. This project mounts dedicated device-authoring instructions there, never the repository coordinator's `AGENTS.md`. [Official managed-agent customization](https://ai.google.dev/gemini-api/docs/custom-agents#skills-skillmd). Inline sources provide the mounted file bytes. [Official environment documentation](https://ai.google.dev/gemini-api/docs/agent-environment).

Review the dedicated [startup instructions](.agents/AGENTS.md) and [device application skill](.agents/skills/device-app-development/SKILL.md) before changing the managed workflow.

Run the examples locally with `python3 -B agent-sdk/run_examples.py`; the same command works at `/workspace/agent-sdk/run_examples.py` in the managed environment. This uses the actual reference runtime, not a device emulator.
