# Current runtime API

The API is declarative JSON interpreted by the installed firmware. There are no arbitrary expressions, script callbacks or hidden peripheral APIs. Read the generated manifest and canonical capabilities for exact limits, layout, versions, fonts and available features.

An app contains identity/version metadata, a fixed display target, theme, initial screen, state and screens. State values are integers or booleans. Each screen has a title and an ordered widget list. IDs are globally unique for widgets and separately unique for screens; references must resolve.

| Widget | Behavior |
| --- | --- |
| `label` | Static text |
| `button` | Label and an ordered `on_press` action list; optional schema-supported background color |
| `counter` | Displays an integer state value, with optional static label |
| `toggle` | Displays and toggles a boolean state value |
| `timer` | Duration, live remaining time and an `on_complete` action list |

| Action | Behavior |
| --- | --- |
| `set` | Assign an existing state's correctly typed value |
| `increment` | Add a fixed integer, with checked integer bounds |
| `toggle` | Invert an existing boolean |
| `navigate` | Enter an existing screen; other actions in the same list still run in order |
| `timer_reset` | Restore initial duration and idle state |
| `timer_start` | Start an idle or paused timer; starting an already-running timer does not restart it |
| `timer_pause` | Pause a running timer while preserving remaining time |

Use composition instead of invented APIs. A finite color cycle can navigate through similarly arranged screens whose buttons have different `background_color` values. State remains shared across screens. A repeated task can reset its state and timer before navigation. Static text changes can use different screens; computed strings are not an implemented feature.

The schema and capabilities are authoritative. Optional button background color is supported by the source runtime that declares it; it does not imply dynamic style actions. Missing color uses the app theme. Firmware chooses contrasting button text.

Camera, microphone, speaker, networking and file APIs are unavailable to generated apps unless the canonical capabilities explicitly implement them. Companion photo/audio/video inputs are separate from device app APIs. No provider key is available to app content.
