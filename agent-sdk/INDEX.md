# SDK index

This is a lookup map, not a required reading checklist. `/workspace/authoring.txt` is the complete generated syntax/requirements brief; read it once and start a runnable request-specific draft. Use `/workspace/agent-sdk/manifest.json` when source versions, canonical hashes or the selected generation profile need checking. It describes source capabilities, not attested device firmware.

Consult [API behavior](api.md) for an unresolved widget/action question, [lifecycle](lifecycle.md) for event/timer ordering, [validation and errors](validation.md) for the checker workflow, or [tools and visual assets](tools-and-assets.md) for research/image boundaries. An example and its scenario can answer a concrete composition question; reading every topic is unnecessary.

Batch independent targeted reads in one `code_execution` call using `rg` or short `sed` ranges. Keep each response below7,500 bytes. Full canonical sources remain available before or after coding, but walking the schema/validator as a checklist is not execution evidence. Run the first draft's checker early, then repair actual defects or investigate specific remaining uncertainties. Examples never replace the user's requested app.

| Example | Files | Behavior |
| --- | --- | --- |
| Counter and reset | `examples/counter.json`, `scenarios/counter.json` | Mutable integer display, repeated increments, reset |
| Shared toggle and navigation | `examples/settings.json`, `scenarios/settings.json` | Boolean state shared between screens |
| Timer controls | `examples/timer.json`, `scenarios/timer.json` | Start, pause, resume, expiry, return/reset |
| Button color cycle | `examples/colors.json`, `scenarios/colors.json` | Same-layout screens with distinct button colors and cyclic navigation |

Run one with `python3 /workspace/agent-sdk/run_examples.py counter`. Run all by omitting the name. Example scenarios establish their own behavior; they do not prove that a new generated app matches the user's intent.

Canonical files are `/workspace/contracts/app.schema.json`, `/workspace/contracts/runtime-capabilities.json`, `/workspace/runtime/validation.py`, `/workspace/runtime/reference.py`, and `/workspace/runtime/scenarios.py`. Consult them without modifying them. Output only the requested artifact in `/workspace/out/app.json` and run `/workspace/trusted_check.py` on its exact bytes.
