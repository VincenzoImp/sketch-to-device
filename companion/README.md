# Android companion

The [interface](index.html), [controller](app.js) and [styles](style.css) are served by the [backend](../backend/README.md). They use browser APIs without build dependencies. All copy is English.

Open the private workspace link containing `#token=...`; the controller removes the fragment from browser history and keeps the demo session token in session storage. Alternatively enter the token from local private provisioning. This is a prepaired single-device demo setup, not public account creation. Never put provider keys in the browser.

The user adds text, up to three images/recordings, or a short microphone recording, then presses **Generate and install**. Microphone capture requires a secure browser origin; file upload is available for native phone recordings. Limits are 12 MB per file and 20 MB combined; microphone recording stops after 30 seconds. Actual Android WebM recording, upload, backend conversion and Gradium transcription have been exercised. Photo/video interpretation remains a separate acceptance gate.

The pending generation request is frozen in session storage before sending. If the response is lost, Resume request retries that same request ID and upload references. Reload resumes an accepted job. Provider progress is distinct from device activation; only the backend's exact acknowledgment match produces the running state. Attachment names and progress are rendered as text, never inserted as HTML.

On 10 October, a real Android voice request reached the installed state at **12:48:46 UTC / 14:48 Europe/Zurich**, after an exact device acknowledgment for the generated app. The user confirmed the phone's installation message and the physical game's Start, scoring, 15-second final score and Play again reset. The same app returned and started after an ordinary reboot without flashing.

The requested title **Rocket Tap** became **Rocket Tata**. Production used generic checks because the transcript missed the narrow tap/duration patterns; an independent check of the exact published app afterward passed the strict 15-second game scenario. This is one real voice-to-device flow with a fidelity defect. A photo-plus-voice **STAR TAP** request for a 20-second game is the next visual test; no result is claimed yet. Full visual-input acceptance, three repeated successful runs and interruption recovery remain pending. See [managed generation evidence](../docs/research/managed-probe.md) for identities and verification scope, and [the ledger](../docs/12-work-ledger.md) for current acceptance.
