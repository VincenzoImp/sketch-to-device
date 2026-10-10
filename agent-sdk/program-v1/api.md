# API and lifecycle

The authoritative signatures and current limits are in
[the canonical contract](../../contracts/programmable.md) and
[profile JSON](../../contracts/program-profile.json). Their managed paths are
`/workspace/program-sdk/contracts/programmable.md` and
`/workspace/program-sdk/contracts/program-profile.json`. They are mounted from the
repository, not copied into this guide. Tool schemas define source/scenario
arguments. Read them before your first tool call.

`app.onTick(fn)` receives one object `{now, delta}` in monotonic milliseconds.
`app.onPointer(fn)` receives `{type, x, y, time}`; types are down/move/up/cancel.
Coordinates are local to the app viewport. Register functions or null to replace
handlers. Keep callbacks short and maintain ordinary JavaScript state between
events. Late ticks coalesce; elapsed-time logic should use `now` rather than
assuming every frame was delivered. `app.now()` uses injected monotonic time.

`app.wallTime()` explicitly reports clock quality. Synchronized time has a
numeric `epochMs`, `valid:true`, `source:'synchronized'`. Estimated time has a
numeric `epochMs`, `valid:false`, `source:'estimated'`. Unavailable time has
`epochMs:null`, `valid:false`, `source:'unavailable'`. An estimated TLS clock
anchor is not accurate wall time. Date is unavailable. `app.random()` and
Math.random use the runtime seed so scenarios can be reproduced.

Compose each visual frame with `gfx.begin(color)`, drawing calls, and `gfx.end()`.
Available drawing calls are rect, line, text and image; consult the contract for
argument order and budgets. Colors use `#RRGGBB`. Images refer to broker-produced
asset IDs. Pixel coordinates and native clipping determine layout; no AppSpec
widget/action vocabulary applies. Make an initial complete frame during startup.

A frame becomes eligible only after its whole callback and Promise checkpoint
succeed. Exceeding execution/drawing limits or throwing an exception fails the
candidate; it does not authorize partial frame publication. Repeated begin/end
does not reset callback budgets. Pause suppresses input/ticks; resume retains
state and resets the delta baseline. The native owner controls JS execution;
apps do not acquire display locks or create native threads.

There is no implicit filesystem, fetch, GPIO, camera, audio, persistent storage,
or firmware API. General algorithms and arbitrary app state are allowed within
the declared modules and resource budgets. New device modules require native
implementation and qualification; research cannot enable them by itself.
