# Provider access probe

The standard-library CLI at `scripts/probe_providers.py` runs on Python 3.9+. It checks the configured providers without installing an SDK, exposing keys, or uploading project/private media. It is supporting preflight tooling, not the application integration.

## Run from an authorized terminal

From the project root:

```sh
python3 -B scripts/probe_providers.py --live
```

The script also works from another directory when invoked by its absolute path. Its default configuration file is the project-root `.env`, regardless of the current directory. Existing `GEMINI_API_KEY` and `GRADIUM_API_KEY` process variables take precedence over that file. Do not pass secret values on the command line or share `.env`.

`--live` permits at most one small authenticated request per selected provider after that host passes DNS and certificate-verified TLS. It does not retry, follow redirects, use environment proxy routes, invoke a shell, or use an alternative network service. It is intended to run where direct provider access is authorized; it does not overcome restrictions in the current execution environment.

Optional modes:

```sh
python3 -B scripts/probe_providers.py
python3 -B scripts/probe_providers.py --live --provider gemini
python3 -B scripts/probe_providers.py --live --provider gradium
python3 -B scripts/probe_providers.py --self-test
```

Without `--live`, only configuration presence and direct DNS/TLS are checked; no key is transmitted. `--self-test` runs isolated synthetic tests without reading the real `.env` or contacting a provider. `--gemini-model` explicitly selects either `gemini-3.8-flash` (default) or the documented `gemini-3.5-flash-lite`; no automatic model substitution occurs. The network budget defaults to 8 seconds per host and the complete request budget to 30 seconds, including response headers. Expiry shuts down the active stream and returns a fixed timeout code. Use `--help` for the bounded timeout options.

## What each live check establishes

| Provider | Request | Passing evidence | Still untested |
|---|---|---|---|
| Gemini | `POST https://generativelanguage.googleapis.com/v1beta/interactions`, `x-goog-api-key` header | HTTP success; matching model; completed interaction; expected fixed reply | Multimodal input, schema generation, tools, managed agent, artifacts |
| Gradium | `GET https://api.gradium.ai/api/usages/credits`, `x-api-key` header | Valid credit response; authenticated account; positive credit availability | STT, TTS, recording formats, actual speech quality |

The Gemini body contains only the selected model, a fixed request for `READY`, `store: false`, and `generation_config.max_output_tokens: 64`. This is a small model call that can consume provider quota. REST uses `steps` containing `model_output` text; an HTTP 200 alone is insufficient. The official schema also permits optional `thinking_level: minimal`; the diagnostic revision omits that setting to reduce optional configuration. Its presence in the earlier request is not evidence that it caused the observed error. [Official REST example](https://ai.google.dev/gemini-api/docs/interactions-overview), [Interactions request and response reference](https://ai.google.dev/api/interactions-api)

Gradium documents integer `remaining_credits` and `allocated_credits`. The CLI reports only whether credits are available, not the balance, plan, or billing details. Zero available credits are distinguished from failed authentication. [Gradium credit API](https://docs.gradium.ai/api-reference/endpoint/get-credits)

Keys are kept in request headers on the verified connection; no credentials enter URL query parameters, process arguments, generated prompts, or output. The response reader caps its body at 64 KiB. Results contain fixed diagnostic codes, booleans, HTTP status, permitted interaction states, and elapsed time. Provider response text, identifiers, arbitrary error messages, and exception representations are omitted.

For Google failures, the CLI permits only known structured error statuses and documented `google.rpc.ErrorInfo` reasons in the `googleapis.com` domain. `API_KEY_INVALID` can mean invalid format, missing key record, or expiry; it cannot identify which of those occurred. Service/application restrictions, disabled services/billing, and quotas have separate fixed diagnostic codes. Unknown reasons, free-text messages, metadata, and identifiers remain omitted. A bare `INVALID_ARGUMENT` does not prove whether the payload or credential caused rejection. [Google error-reason definitions](https://github.com/googleapis/googleapis/blob/master/google/api/error_reason.proto), [Google structured errors](https://google.aip.dev/193)

## Interpreting results

- `blocked_by_network` with `dns_unavailable`: the service was not reached. This says nothing about key validity, balance, model access, or the user's account.
- `network_ready_live_not_requested`: DNS/TLS and local key presence passed; authentication was deliberately not tested.
- `authentication_rejected`, `permission_rejected`, or `quota_or_rate_limit`: the live request received a corresponding HTTP status; inspect account configuration through its normal private interface.
- `route_or_model_unavailable`: the chosen endpoint/model was unavailable to this request. Do not silently replace the event model.
- `api_key_invalid_or_expired`, `api_key_service_blocked`, `api_key_application_blocked`, `service_disabled`, or `billing_disabled`: Google supplied a corresponding allowlisted structured reason. Authentication remains unverified; no inference is made from the key's appearance.
- `authenticated_no_credits`: Gradium returned a valid account response without positive available credits; speech remains untested.
- `interaction_not_completed`, `unexpected_model_output`, or response-shape errors: the required model smoke test did not pass. The script never reports an incomplete interaction as success.
- `passed`: the selected minimal live check succeeded. The output still lists untested media, managed-agent, speech, and hardware capabilities.

Exit code `0` means all checks requested by that mode passed. For default mode this only means configuration and network checks. Exit `1` means a requested check failed or was blocked; `2` indicates invalid arguments/configuration or an internal failure; `130` means interruption.

## Evidence from this execution environment

On **10 October 2026 at 10:21:24 UTC**, the command `python3 scripts/probe_providers.py --live` exited `1`:

| Provider | Private key presence | DNS | TLS | Authenticated request |
|---|---|---|---|---|
| Gemini | Configured | Failed: `dns_unavailable` | Not attempted | Not attempted |
| Gradium | Configured | Failed: `dns_unavailable` | Not attempted | Not attempted |

Each official host received one DNS attempt. The dependent request was skipped. There was no successful provider authentication, model output, or credit response. Do not repeat this same live command in the unchanged restricted session; rerun once in an authorized normal terminal or after a material network/execution change. The script itself does not change permissions or network policy.

## Evidence reported from the user's terminal

The user ran the live command in their normal terminal and shared its redacted result dated **10 October 2026 at 10:28:25 UTC**. This is user-provided execution evidence, not a successful call from the restricted agent shell:

| Provider | DNS/TLS | HTTP | Observed result |
|---|---|---|---|
| Gradium | Passed | 200 | Authentication confirmed; credits available |
| Gemini `gemini-3.8-flash` | Passed | 400 | `request_rejected`; authentication unverified; elapsed 791 ms |

Gradium speech recognition remains untested. The initial Gemini output intentionally omitted all response details, so its cause is not known. The revised classifier can distinguish recognized structured Google reasons without exposing the response. The user then checked Gemini alone with:

```sh
python3 -B /Users/vincenzo/hackathon/scripts/probe_providers.py --live --provider gemini
```

The user ran that revised command and shared a second result dated **10 October 2026 at 10:32:53.476642 UTC**: Gemini `gemini-3.8-flash` passed DNS/TLS, returned HTTP 200, confirmed authentication, reached `completed`, and matched the expected reply; elapsed time was **2071 ms**. The same configured key was used, and the optional `thinking_level` setting had been omitted. This establishes that the simplified request passes; it does not prove the cause of the previous HTTP 400, whose structured reason was not captured. Both providers' minimal checks have now passed in the user's terminal. Managed-agent execution, artifacts, media, Gradium speech and physical-device behavior remain separate gates.

## Tool validation

`python3 -B scripts/probe_providers.py --self-test` passed **18 synthetic tests**. They cover configuration parsing and environment precedence, header-injection rejection, DNS failure/timeout, certificate rejection, skipped authentication after network failure and without `--live`, safe exception/argument output, HTTP errors and redirects, allowlisted Google error classification and unknown-error redaction, credit-response validation, incomplete Gemini results, response size bounds, bounded waiting for stalled headers, and chunked/connection-close handling through Python's real HTTP parser with an in-memory socket. These are **unit-only results**, not evidence of live provider availability or speech processing.

The timeout revision passed independent review and an independent delayed-header reproduction. The error-classifier revision also passed focused independent review, including wrong-type/domain rejection, bare `INVALID_ARGUMENT`, private metadata redaction and the captured request body. The coordinator records that review and current ownership in the [work ledger](../12-work-ledger.md), and updates the [readiness register](../11-readiness.md) with the next real probe outcome.

## Smallest next integration checks

1. Preserve the successful minimal-provider results; no unchanged retry is needed.
2. Test the separate managed-agent command/artifact path described in [Gemini research](gemini.md). This CLI intentionally does not claim that capability.
3. Record a short real English request on the Android phone. Verify its actual media format, convert to supported WAV, and send it through Gradium STT using the contract in [partner research](partners.md). A credit GET cannot substitute for this speech test.
4. Link actual provider results into a generation job and then the physical-device path. None of those product steps is implemented by this probe.
