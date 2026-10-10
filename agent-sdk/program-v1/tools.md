# Trusted tool workflow

The function schemas supplied to this interaction are authoritative for argument
shape. Do not invent fields or host paths.

- `prepare_uploaded_asset`: select a job-owned upload and explicitly request
  supported crop/resize conversion. It returns a server asset identifier and
  dimensions. Preserve the original's provenance; the JPEG used for perception
  is not automatically the asset to install. Arbitrary URLs, host paths and new
  image generation are not implicit capabilities.
- `run_app`: send freshly authored source, identity/title, required modules,
  chosen server assets and a bounded scenario. The broker assembles immutable
  package bytes before launching its pinned native runner. Inspect the actual
  returned images and execution feedback. Changing any code, metadata, asset or
  scenario requires a new run and receipt.
- `submit_app`: pass only a successful server receipt ID. The broker verifies
  job ownership, current intent and exact candidate identity; the adapter returns
  that selection to its caller. The caller performs publication. A receipt is not
  proof of installation; only the device's exact acknowledgment establishes that.

Tool failures marked repairable return feedback through the same call ID. Fix
the cause and run again, rather than retrying unchanged invalid data. A second
identical failure stops a stalled loop. Deadline, transport and malformed
protocol failures do not trigger an automatic new generation or model switch.

Remote code execution can help author and inspect source, but cannot impersonate
the trusted native runner. Printed markers, fabricated receipts, model-authored
test summaries and final prose cannot select a package. Do not include secrets
or private input in searches. Backend tool results and screenshots return in the
same managed environment through correlated function results.
