"""Strict AppSpec v1 parsing and validation; no generated code is executed."""

import hashlib
import json
import re
from pathlib import Path


CAPABILITIES_PATH = Path(__file__).resolve().parents[1] / "contracts/runtime-capabilities.json"
CAPABILITIES = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
LIMITS = CAPABILITIES["limits"]
INT_MIN, INT_MAX = -(2 ** 31), 2 ** 31 - 1
ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,47}", re.ASCII)


class ValidationError(ValueError):
    def __init__(self, code, path, message):
        self.code, self.path, self.message = code, path, message
        super().__init__("{} at {}: {}".format(code, path, message))

    def as_dict(self):
        return {"code": self.code, "path": self.path, "message": self.message}


def fail(code, path, message):
    raise ValidationError(code, path, message)


def _object(value, required, optional, path):
    if type(value) is not dict:
        fail("type", path, "Expected an object")
    if set(value) - set(required) - set(optional):
        fail("unknown_field", path, "Object contains unsupported fields")
    if set(required) - set(value):
        fail("required", path, "Object is missing required fields")


def _integer(value, lower, upper, path):
    if type(value) is not int or not lower <= value <= upper:
        fail("integer", path, "Expected an integer in the allowed range")


def _identifier(value, path):
    if type(value) is not str or not ID_PATTERN.fullmatch(value):
        fail("identifier", path, "Expected a lowercase ASCII identifier")


def _text(value, path, maximum=120):
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or any(not 32 <= ord(char) <= 126 for char in value)):
        fail("text", path, "Expected nonempty supported printable ASCII text")


def _list(value, lower, upper, path):
    if type(value) is not list or not lower <= len(value) <= upper:
        fail("count", path, "Expected an array within the allowed count")


def _preflight_depth(text):
    """Bound container nesting before JSON constructs an object tree."""
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > LIMITS["max_json_depth"]:
                fail("depth", "$", "JSON exceeds the container depth limit")
        elif char in "]}":
            depth -= 1


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("duplicate_key", "$", "JSON object repeats a key")
        result[key] = value
    return result


def _reject_number(value):
    fail("number", "$", "Only integer JSON number syntax is supported")


def decode_json(raw):
    """Decode bounded UTF-8 JSON, rejecting duplicate keys and non-integers."""
    if type(raw) is not bytes:
        fail("type", "$", "Package input must be bytes")
    if len(raw) > LIMITS["max_app_bytes"]:
        fail("bytes", "$", "Package exceeds 64 KiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("encoding", "$", "Package must be UTF-8")
    _preflight_depth(text)
    try:
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_float=_reject_number, parse_constant=_reject_number)
    except ValidationError:
        raise
    except (ValueError, RecursionError):
        fail("json", "$", "Malformed JSON")
    return value


def parse_app(raw):
    """Validate exact UTF-8 package bytes, returning a fresh trusted model."""
    app = decode_json(raw)
    validate_app(app)
    return app


def load_app(path):
    with open(path, "rb") as source:
        raw = source.read(LIMITS["max_app_bytes"] + 1)
    return parse_app(raw)


def package_report(raw):
    app = parse_app(raw)
    return {"valid": True, "app_id": app["app_id"], "version": app["version"],
            "schema_version": app["schema_version"], "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "validator_version": CAPABILITIES["runtime_version"],
            "evidence": "host_validation_only"}


def _state_value(value, path):
    if type(value) is not bool:
        _integer(value, INT_MIN, INT_MAX, path)


def validate_app(app):
    """Semantic/layout validation; untrusted input must enter through parse_app."""
    _object(app, ("schema_version", "app_id", "version", "name", "target", "theme",
                  "initial_screen", "state", "screens"), (), "$")
    _integer(app["schema_version"], 1, 1, "$.schema_version")
    _identifier(app["app_id"], "$.app_id")
    _integer(app["version"], 1, INT_MAX, "$.version")
    _text(app["name"], "$.name", 48)
    target = app["target"]
    _object(target, ("width", "height", "orientation"), (), "$.target")
    _integer(target["width"], 320, 320, "$.target.width")
    _integer(target["height"], 480, 480, "$.target.height")
    if target["orientation"] != "portrait":
        fail("enum", "$.target.orientation", "Only portrait is supported")
    theme = app["theme"]
    _object(theme, ("palette", "font_size"), (), "$.theme")
    if type(theme["palette"]) is not str or theme["palette"] not in CAPABILITIES["palettes"]:
        fail("enum", "$.theme.palette", "Unsupported palette")
    if type(theme["font_size"]) is not str or theme["font_size"] not in CAPABILITIES["fonts"]:
        fail("enum", "$.theme.font_size", "Unsupported font preset")
    state = app["state"]
    if type(state) is not dict or len(state) > LIMITS["max_state_values"]:
        fail("state", "$.state", "Expected a bounded state object")
    for key, value in state.items():
        _identifier(key, "$.state")
        _state_value(value, "$.state." + key)
    _list(app["screens"], 1, LIMITS["max_screens"], "$.screens")
    screens, widgets, timers = {}, {}, {}
    for index, screen in enumerate(app["screens"]):
        path = "$.screens[{}]".format(index)
        _object(screen, ("id", "title", "widgets"), (), path)
        _identifier(screen["id"], path + ".id")
        if screen["id"] in screens:
            fail("duplicate_id", path, "Repeated screen ID")
        screens[screen["id"]] = screen
        _text(screen["title"], path + ".title")
        _list(screen["widgets"], 0, LIMITS["max_widgets_per_screen"], path + ".widgets")
        for offset, widget in enumerate(screen["widgets"]):
            widget_path = path + ".widgets[{}]".format(offset)
            if type(widget) is not dict:
                fail("type", widget_path, "Expected a widget object")
            kind = widget.get("type")
            fields = {
                "label": (("text",), ()),
                "button": (("text", "on_press"), ()),
                "counter": (("state_key",), ("text",)),
                "toggle": (("state_key", "text"), ()),
                "timer": (("duration_seconds", "on_complete"), ("text",)),
            }
            if type(kind) is not str or kind not in fields:
                fail("enum", widget_path, "Unsupported widget type")
            required, optional = fields[kind]
            _object(widget, ("id", "type") + required, optional, widget_path)
            _identifier(widget["id"], widget_path + ".id")
            if widget["id"] in widgets:
                fail("duplicate_id", widget_path, "Widget IDs must be globally unique")
            widgets[widget["id"]] = widget
            if "text" in widget:
                _text(widget["text"], widget_path + ".text")
            if kind in ("counter", "toggle"):
                _state_ref(widget["state_key"], state, int if kind == "counter" else bool, widget_path)
            if kind == "timer":
                _integer(widget["duration_seconds"], 1, 3600, widget_path + ".duration_seconds")
                timers[widget["id"]] = widget
    if len(widgets) > LIMITS["max_widgets_total"] or len(timers) > LIMITS["max_timers"]:
        fail("count", "$.screens", "Too many widgets or timers")
    _identifier(app["initial_screen"], "$.initial_screen")
    if app["initial_screen"] not in screens:
        fail("reference", "$.initial_screen", "Initial screen does not exist")
    graph = {screen_id: set() for screen_id in screens}
    started = {screen_id: set() for screen_id in screens}
    for screen_id, screen in screens.items():
        for widget in screen["widgets"]:
            for event in ("on_press", "on_complete"):
                if event not in widget:
                    continue
                path = "$.widgets." + widget["id"] + "." + event
                _list(widget[event], 0, LIMITS["max_actions_per_event"], path)
                for action in widget[event]:
                    _action(action, state, screens, timers, event == "on_complete", path)
                    if event == "on_press" and action["type"] == "navigate":
                        graph[screen_id].add(action["screen_id"])
                    elif event == "on_press" and action["type"] == "timer_start":
                        started[screen_id].add(action["widget_id"])
        _layout(screen)
    for screen_id, timer_ids in started.items():
        for timer_id in timer_ids:
            # Timers are global; their view need not have been rendered.
            for action in timers[timer_id]["on_complete"]:
                if action["type"] == "navigate":
                    graph[screen_id].add(action["screen_id"])
    reachable = {app["initial_screen"]}
    pending = list(reachable)
    while pending:
        for destination in graph[pending.pop()] - reachable:
            reachable.add(destination)
            pending.append(destination)
    if reachable != set(screens):
        fail("unreachable", "$.screens", "Every screen must be structurally reachable")


def _state_ref(key, state, expected, path):
    _identifier(key, path + ".state_key")
    if key not in state or (expected is not None and type(state[key]) is not expected):
        fail("reference", path, "State reference is missing or has the wrong type")


def _action(action, state, screens, timers, completion, path):
    if type(action) is not dict:
        fail("type", path, "Expected an action object")
    kind = action.get("type")
    fields = {"navigate": ("screen_id",), "set": ("state_key", "value"),
              "increment": ("state_key", "amount"), "toggle": ("state_key",),
              "timer_start": ("widget_id",), "timer_pause": ("widget_id",),
              "timer_reset": ("widget_id",)}
    if type(kind) is not str or kind not in fields:
        fail("enum", path, "Unsupported action type")
    if completion and kind.startswith("timer_"):
        fail("completion_action", path, "Completion handlers cannot control timers")
    _object(action, ("type",) + fields[kind], (), path)
    if kind == "navigate":
        _identifier(action["screen_id"], path + ".screen_id")
        if action["screen_id"] not in screens:
            fail("reference", path, "Screen reference does not exist")
    elif kind.startswith("timer_"):
        _identifier(action["widget_id"], path + ".widget_id")
        if action["widget_id"] not in timers:
            fail("reference", path, "Timer reference does not exist")
    else:
        expected = {"increment": int, "toggle": bool, "set": None}[kind]
        _state_ref(action["state_key"], state, expected, path)
        if kind == "set":
            _state_value(action["value"], path + ".value")
            if type(action["value"]) is not type(state[action["state_key"]]):
                fail("type", path, "Set must preserve the declared state type")
        elif kind == "increment":
            _integer(action["amount"], INT_MIN, INT_MAX, path + ".amount")


def _layout(screen):
    layout = CAPABILITIES["layout"]
    width = CAPABILITIES["app_viewport"]["width"] - 2 * layout["padding_px"]
    glyph = CAPABILITIES["fonts"]["medium"]["max_glyph_width_px"]
    line = CAPABILITIES["fonts"]["medium"]["line_height_px"]

    def text_height(text, available):
        columns = available // glyph
        return ((len(text) + columns - 1) // columns) * line if text else 0

    height = 2 * layout["padding_px"] + text_height(screen["title"], width)
    for widget in screen["widgets"]:
        kind = widget["type"]
        available = width
        if kind != "label":
            available -= 2 * layout["control_padding_px"]
        if kind == "toggle":
            available -= layout["toggle_indicator_px"]
        content = text_height(widget.get("text", ""), available)
        if kind in ("counter", "timer"):
            content += line  # Includes the worst-case signed 32-bit value / 3600 seconds.
        if kind != "label":
            content = max(layout["min_control_height_px"], content + 2 * layout["control_padding_px"])
        height += layout["gap_px"] + content
    if height > CAPABILITIES["app_viewport"]["height"]:
        fail("layout", "$.screens." + screen["id"], "Content exceeds the reserved app viewport")
