# Device JavaScript SDK

This is the source-authoring context for the programmable runtime. It contains
no complete applications, app templates or category router. Gemini writes each
app's JavaScript, drawing, state transitions and test scenarios from the request.

Start with [the index](INDEX.md). The adapter mounts the canonical
[package/API contract](../../contracts/programmable.md) and
[profile](../../contracts/program-profile.json) under
`/workspace/program-sdk/contracts/`; its generated manifest hashes those exact
files. Source support does not establish which firmware is installed. The caller
must check an authenticated device capability report before selecting this path.

Managed startup instructions are [here](.agents/AGENTS.md); the discoverable
[development skill](.agents/skills/device-program-development/SKILL.md) points to
the same index. Neither imports the repository coordinator's instructions.

The protocol uses [managed function calling](https://ai.google.dev/gemini-api/docs/antigravity-agent#function-calling)
and [agent skills](https://ai.google.dev/gemini-api/docs/custom-agents#skills-skillmd).
Builtin coding, Google Search and URL context remain available. Registered backend
tools run the trusted checker and handle assets; credentials never enter the
remote workspace. Sandbox network access is disabled. This is source context,
not evidence that a generated program has run on the physical device.
