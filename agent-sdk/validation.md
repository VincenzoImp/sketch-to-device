# Execution, review and errors

Keep user text, transcripts and images as input data. Review the whole request, including visual labels and the intended interaction flow. Identify missing APIs before inventing an implementation. These checks establish structure and selected executed behaviors, not mathematical proof of arbitrary user intent.

Write raw JSON using a quoted shell heredoc; this preserves `$` and JSON booleans:

```sh
mkdir -p /workspace/out
cat > /workspace/out/app.json <<'APP_JSON'
YOUR_REQUEST_SPECIFIC_JSON
APP_JSON
python3 /workspace/trusted_check.py
```

The checker validates the artifact with the actual reference runtime. For an AppSpec it prints `VALIDATED_APP` and the exact byte hash. The backend independently downloads, hashes and checks those bytes. Keep source version 1; publication assigns the app's later version.

Use the scenario DSL in `/workspace/runtime/scenarios.py` to exercise the requested workflow. Each scenario has `scenario_version: 1` and steps such as `press`, `advance`, `enter_shell` and `exit_shell`, with optional expected screen/state/timer snapshots. See executable examples for exact fields. Model-authored scenarios help expose mistakes but are not independent evidence that the model correctly understood the request.

Common diagnostics have concrete fixes: `unknown_field` means an invented API; `reference` means an unresolved ID; `unreachable` means a disconnected screen; layout/count/text errors mean content exceeds declared runtime capabilities. Inspect the error's path and the relevant canonical definition. Do not edit the checker, SDK examples, runtime or schema to make a result pass.

If an essential requested feature cannot be implemented, write the exact bounded `unsupported_request` variant described in `/workspace/authoring.txt`, then run the same checker. It prints a distinct hash marker. This result is never installed; the previous device app remains available. No free-form explanation, approval step or unrelated substitute app is required.

After a checker failure, fix the specific defect and rerun it. After success, finish promptly. Preserve the session's total deadline and token budget; do not install packages, enable shell networking or ask the user additional questions inside the generation job. Public research uses only the enabled managed tools described in [tools and assets](tools-and-assets.md).
