# SDK index

Use `/workspace/agent-sdk/manifest.json` for source version, canonical paths and hashes. It describes source capabilities, not attested device firmware.

1. Read `/workspace/authoring.txt` for generated schema syntax and exact extracted requirements.
2. Consult [API behavior](api.md) for widgets/actions and state, [lifecycle](lifecycle.md) for event/timer order, [validation and errors](validation.md) for the execution workflow, and [tools and visual assets](tools-and-assets.md) for current research/image boundaries.
3. Inspect the relevant example and its scenario. Combine primitives freely to serve the actual input; do not copy an unrelated example as the answer.
4. Use targeted `rg -n` or short `sed -n` ranges on canonical files when the guide does not resolve a question. Keep each tool response below 7,500 bytes and avoid dumping an entire source tree or schema.

| Example | Files | Behavior |
| --- | --- | --- |
| Counter and reset | `examples/counter.json`, `scenarios/counter.json` | Mutable integer display, repeated increments, reset |
| Shared toggle and navigation | `examples/settings.json`, `scenarios/settings.json` | Boolean state shared between screens |
| Timer controls | `examples/timer.json`, `scenarios/timer.json` | Start, pause, resume, expiry, return/reset |
| Button color cycle | `examples/colors.json`, `scenarios/colors.json` | Same-layout screens with distinct button colors and cyclic navigation |

Run one with `python3 /workspace/agent-sdk/run_examples.py counter`. Run all by omitting the name. Example scenarios establish their own behavior; they do not prove that a new generated app matches the user's intent.

Canonical files are `/workspace/contracts/app.schema.json`, `/workspace/contracts/runtime-capabilities.json`, `/workspace/runtime/validation.py`, `/workspace/runtime/reference.py`, and `/workspace/runtime/scenarios.py`. Consult them without modifying them. Output only the requested artifact in `/workspace/out/app.json` and run `/workspace/trusted_check.py` on its exact bytes.
