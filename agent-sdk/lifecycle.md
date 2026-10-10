# Event and application lifecycle

The source of truth is `/workspace/runtime/reference.py` for event semantics and `/workspace/runtime/validation.py` for accepted structure. The reference runtime is an executable model, not a hardware simulator.

- Installing a valid app initializes state and enters its initial screen. Invalid replacement input must preserve the previous app.
- Before processing a press, advance timers to that monotonic timestamp. A timer expiring exactly at a press timestamp completes first. A press targeting the previous screen is then ignored.
- A button's actions execute in order against one candidate state. An action error rejects the action list without partially committing state changes. A timer expiry itself remains completed even if its handler fails.
- Only current-screen controls with a current activation/screen event token accept input. Navigation, including re-entering a screen, invalidates stale event tokens.
- State and timers belong to the app, not a screen. Navigation alone does not reset them. Reset explicitly when the requested behavior requires it.
- Entering the device shell pauses countdown advancement; returning resumes the remaining time. App state is not promised to persist across reboot: loading the package initializes its declared state again.

Package handling is separate from these app events. The backend validates the downloaded artifact and assigns the published version. Device delivery verifies the exact package identity/hash, writes an inactive slot, activates it and acknowledges it. An agent's completion message is not installation evidence. Firmware flashing is a separate setup operation and is not an app action.
