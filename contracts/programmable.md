# Programmable package and execution contract

Revision1, implementation contract for D30. This contract is **not a capability
announcement**. The installed device remains AppSpec0.2. The first new profile is
defined in [program-profile.json](program-profile.json); physical qualification
and later dynamic-control/device modules remain release gates in
[the platform plan](../docs/16-final-platform-plan.md).

## Immutable package

Schema1 remains unchanged. Schema2 is UTF-8 JSON with exactly these fields:

| Field | Value |
| --- | --- |
| `schema_version` | Integer2 |
| `app_id` | Lowercase ASCII identifier, `[a-z][a-z0-9_-]{0,47}` |
| `name` | 1..48 printable ASCII characters, display title |
| `version` | Server-reserved integer1..2147483647 |
| `runtime` | `quickjs-ng-0.14.0` |
| `sdk` | `device-js-1` |
| `profile` | `p4-canvas-1` |
| `requires` | Distinct module names from the profile, possibly empty |
| `source` | Nonempty UTF-8 JavaScript source; no NUL or unpaired surrogate |
| `assets` | Array of immutable image entries described below, possibly empty |

No bytecode, native code, external asset URLs, host paths, model-provided receipts
or firmware operations are accepted. This does not restrict JavaScript
algorithms to named app categories. Source syntax and actual execution are
checked by the pinned engine, not inferred by a regular expression.

Each asset has exactly `id`, `width`, `height`, `format`, `sha256`, `data_b64`.
IDs use the same identifier grammar and are unique within the package.
`format` is `rgba8888`: row-major tightly packed bytes R,G,B,A, unpremultiplied,
no padding, exactly `width * height * 4` bytes. The lowercase SHA256 covers those
decoded bytes. Base64 is canonical RFC4648, with padding and no whitespace.
Width is1..320 and height1..432. The native renderer converts channel ordering
explicitly; host endianness must not redefine the wire format. Rendering never
mutates asset bytes. Conversion must preserve source provenance outside the
public package, in job-owned server records.

The whole serialized package is at most65,536bytes. At most32 assets and
49,152decoded asset bytes are an initial software profile, **not hardware
capacity claims**. The envelope also bounds source; escaped JSON can be larger
than its source string. The server reports a resource error rather than silently
discarding requested behavior. Profile enlargement requires measured
memory/storage/recovery evidence. Larger phone uploads do not change this
device envelope.

Strict parsing rejects duplicate keys, unsupported fields, noninteger metadata,
invalid UTF-8, NUL, unpaired surrogates and excessive JSON depth. Version/name
and all package fields are assigned or validated before execution. Final bytes
are frozen before issuing any successful runner receipt. Publication must not
reformat JSON, change the version, or substitute assets afterward.

## Shared runtime surface

The initial generic module contract is:

- `app.onTick(fn)`: replace the handler (function or null), called with
  `{now, delta}` in monotonic milliseconds. The native owner supplies
  monotonic time, coalesces late ticks and never builds an unbounded backlog.
- `app.onPointer(fn)`: replace the handler (function or null), called with
  `{type, x, y, time}` where type is down/move/up/cancel and time is captured
  monotonic milliseconds; coordinates are relative to
  the320x432 app viewport. System controls remain outside it.
- `app.now()`: current injected monotonic milliseconds, independent of wall time.
- `app.wallTime()`: `{epochMs, valid, source}`, with epochMs null only when unavailable and
  source unavailable/estimated/synchronized; only synchronized is valid. An
  estimated numeric epoch remains available with valid false. A build-time
  TLS fallback is not accurate synchronized time.
- `app.random()`: runtime-owned seeded generator; host tests provide the seed.
- `gfx.begin(color)`, `gfx.rect(x,y,w,h,color)`,
  `gfx.line(x1,y1,x2,y2,color,width)`, `gfx.text(x,y,text,color)`,
  `gfx.image(assetId,x,y)`, `gfx.end()`: append one bounded drawing batch.

Color strings are `#RRGGBB`. Initial per-callback limits are128 drawing commands,
256UTF-8bytes per text,4096total text bytes and552,960clipped pixel-work units.
Repeated begin/end cannot reset the budgets. The native core owns validation,
clipping and budget enforcement. Native error codes are frozen with its public
header and actual tests before generation is activated. Pause suppresses tick
and input; resume retains JS state and resets the tick delta baseline. Both
app.random and Math.random use the injected seed. Date is initially unavailable;
wall time uses the explicit app API so tests never consult the host clock.
The API above is the first implementation slice; general controls/layout,
additional drawing operations and device services extend the versioned SDK.
It is not the finished platform's maximum API surface.

JavaScript handlers and pending Promise jobs execute on one app owner thread,
outside the BSP display lock. A frame is eligible only after the whole callback
and its microtask checkpoint succeed. Native LVGL drawing/presentation occurs
under the display lock afterward. Engine heap/stack, native allocations, assets,
framebuffers and retained previous/candidate apps are different memory budgets.
An engine memory limit alone does not contain all native failures.

## Trusted execution and agent tools

The product agent keeps its managed coding/filesystem/search tools. Custom
functions add specific trusted services; they are not host shell passthrough.

1. `prepare_uploaded_asset` resolves a job-owned upload, performs declared
   crop/resize conversion and returns an opaque server asset ID and dimensions.
   It accepts neither arbitrary file paths nor URLs. Original media stays
   separate from perception JPEGs.
2. `run_app` accepts generated source, title/ID, required modules, server asset
   IDs and a bounded scenario. The server reserves identity/version, assembles
   immutable bytes and independently validates them before launching its pinned
   runner. Actual logs, failure diagnostics and rendered images return through
   the correlated function result. Agent-authored scenarios are untrusted input.
3. `submit_app` accepts a server receipt ID only. The server looks it up under
   this authenticated job, checks candidate/SDK/runner/scenario identity and
   current install intent, then durably selects those bytes. The agent loop
   returns that trusted selection; its caller publishes unchanged bytes exactly
   once. The tool itself does not install or publish an app.

A receipt records job, candidate ID/hash/size, engine/SDK/profile, runner build
fingerprint, scenario hash, execution status, observed diagnostics and frame
hashes. It is generated from the actual process result and stored server-side;
an agent-written marker, JSON object or statement is never evidence of a run.
Receipts do not prove all user requirements: independent behavioral tests and
physical acceptance remain necessary. Resource exhaustion and run failure
return repair feedback without installing anything.

The runner process receives only the immutable candidate and scenario in a
private temporary directory. No API keys, service tokens, uploaded-original
paths or arbitrary command strings enter its environment. It cannot access
filesystem/network through the JS API. The host enforces a process deadline
outside engine interrupts and captures bounded output. These are practical
containment measures, not a proof against every native implementation defect.

Provider call IDs, interaction/environment IDs and tool results must correlate
before continuation. Persist handles before work; retain the last authenticated
handle on malformed responses or cancellation. Terminating observation is not
evidence of remote termination. No duplicate generation or automatic new job
is started merely because a poll timed out.

## Device compatibility and recovery

The backend must use a fresh authenticated device report identifying installed
runtime, engine, SDK/profile and modules. Do not serve the source profile as a
device capability declaration. Legacy devices remain on schema1.

Preparation, activation and healthy execution are distinct. Candidate admission
or initialization failure preserves the existing app. After activation, an
exception/resource failure must recover the actual prior identity and persist
a recovery outbox entry across disconnect/reboot. The backend must invalidate
current-health claims for the failed activation, without rewriting its
historical installation acknowledgment. Quarantine interrupted/crashing
activations to avoid a boot loop. Two complete packages and metadata must fit
the existing storage before increasing this profile; no storage erase is part
of ordinary app installation.
