"""Deterministic AppSpec state machine. This is not a hardware emulator."""

from copy import deepcopy
from dataclasses import dataclass

from .validation import INT_MAX, INT_MIN, parse_app


class RuntimeEventError(ValueError):
    """An event was rejected without committing its action list."""


@dataclass(frozen=True)
class EventToken:
    activation_id: int
    screen_entry: int


class ReferenceRuntime:
    def __init__(self, raw, now_ms=0):
        self.now_ms = 0
        self.activation_id = 0
        self.screen_entry = 0
        self.errors = []
        self.install(raw, now_ms)

    def _clock(self, now_ms):
        if type(now_ms) is not int or now_ms < self.now_ms:
            raise ValueError("Time must be monotonic integer milliseconds")
        self.now_ms = now_ms

    def install(self, raw, now_ms):
        # Parse before changing anything: invalid replacements preserve the current app.
        app = parse_app(raw)
        self._clock(now_ms)
        self.app = app
        self.activation_id += 1
        self.screen_entry += 1
        self.state = deepcopy(app["state"])
        self.screen = app["initial_screen"]
        self.in_shell = False
        self.widgets = {widget["id"]: widget for screen in app["screens"] for widget in screen["widgets"]}
        self.visible = {screen["id"]: {widget["id"] for widget in screen["widgets"]} for screen in app["screens"]}
        self.timers = {
            widget_id: {"status": "idle", "remaining_ms": widget["duration_seconds"] * 1000,
                        "deadline_ms": None}
            for widget_id, widget in self.widgets.items() if widget["type"] == "timer"
        }

    def event_token(self):
        return EventToken(self.activation_id, self.screen_entry)

    def _actions(self, actions):
        state, timers = deepcopy(self.state), deepcopy(self.timers)
        screen, entry = self.screen, self.screen_entry
        for action in actions:
            kind = action["type"]
            key = action.get("state_key")
            if kind == "navigate":
                screen = action["screen_id"]
                entry += 1  # Includes navigation back to the same named screen.
            elif kind == "set":
                state[key] = action["value"]
            elif kind == "increment":
                value = state[key] + action["amount"]
                if not INT_MIN <= value <= INT_MAX:
                    raise RuntimeEventError("Signed 32-bit increment overflow")
                state[key] = value
            elif kind == "toggle":
                state[key] = not state[key]
            else:
                widget_id = action["widget_id"]
                timer = timers[widget_id]
                if kind == "timer_reset":
                    timer.update(status="idle", remaining_ms=self.widgets[widget_id]["duration_seconds"] * 1000,
                                 deadline_ms=None)
                elif kind == "timer_start" and timer["status"] in ("idle", "paused"):
                    timer.update(status="running", deadline_ms=self.now_ms + timer["remaining_ms"])
                elif kind == "timer_pause" and timer["status"] == "running":
                    timer.update(status="paused", remaining_ms=max(0, timer["deadline_ms"] - self.now_ms),
                                 deadline_ms=None)
        self.state, self.timers, self.screen, self.screen_entry = state, timers, screen, entry

    def advance(self, now_ms):
        """Scheduler entry point, also called before every user/shell event."""
        self._clock(now_ms)
        if self.in_shell:
            return
        due = sorted((timer["deadline_ms"], widget_id) for widget_id, timer in self.timers.items()
                     if timer["status"] == "running" and timer["deadline_ms"] <= now_ms)
        for _, widget_id in due:
            # Expiry is a scheduler fact even if its handler fails. It must never fire again.
            self.timers[widget_id].update(status="completed", remaining_ms=0, deadline_ms=None)
            try:
                self._actions(self.widgets[widget_id]["on_complete"])
            except RuntimeEventError as error:
                self.errors.append({"event": "timer_complete", "widget_id": widget_id, "error": str(error)})

    def press(self, widget_id, now_ms, token):
        self.advance(now_ms)
        if self.in_shell or token != self.event_token() or widget_id not in self.visible[self.screen]:
            return "ignored"
        widget = self.widgets[widget_id]
        if widget["type"] == "button":
            actions = widget["on_press"]
        elif widget["type"] == "toggle":
            actions = [{"type": "toggle", "state_key": widget["state_key"]}]
        else:
            return "ignored"
        try:
            self._actions(actions)
        except RuntimeEventError as error:
            self.errors.append({"event": "press", "widget_id": widget_id, "error": str(error)})
            return "rejected"
        return "applied"

    def enter_shell(self, now_ms):
        self.advance(now_ms)
        if self.in_shell:
            return
        for timer in self.timers.values():
            if timer["status"] == "running":
                timer["remaining_ms"] = max(0, timer["deadline_ms"] - now_ms)
                timer["deadline_ms"] = None
        self.in_shell = True
        self.screen_entry += 1

    def exit_shell(self, now_ms):
        self._clock(now_ms)
        if not self.in_shell:
            self.advance(now_ms)
            return
        for timer in self.timers.values():
            if timer["status"] == "running":
                timer["deadline_ms"] = now_ms + timer["remaining_ms"]
        self.in_shell = False
        self.screen_entry += 1

    def snapshot(self):
        timers = deepcopy(self.timers)
        for timer in timers.values():
            if timer["status"] == "running" and not self.in_shell:
                timer["remaining_ms"] = max(0, timer["deadline_ms"] - self.now_ms)
            timer.pop("deadline_ms")
        return {"screen": self.screen, "state": deepcopy(self.state), "timers": timers,
                "in_shell": self.in_shell, "activation_id": self.activation_id,
                "screen_entry": self.screen_entry}
