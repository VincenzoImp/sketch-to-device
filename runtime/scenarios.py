"""Run bounded data-only scenarios with independent expected outcomes."""

from .validation import ValidationError, decode_json


def _expect(actual, expected, path="snapshot"):
    if type(expected) is dict:
        if type(actual) is not dict:
            raise AssertionError("Expected an object at " + path)
        if not expected and actual:
            raise AssertionError("Expected an empty object at " + path)
        for key, value in expected.items():
            if key not in actual:
                raise AssertionError("Missing expected field at " + path)
            _expect(actual[key], value, path + "." + key)
    elif type(actual) is not type(expected) or actual != expected:
        raise AssertionError("Scenario expectation failed at " + path)


def run_scenario(runtime, raw):
    scenario = decode_json(raw)
    if (type(scenario) is not dict or set(scenario) != {"scenario_version", "steps"}
            or type(scenario["scenario_version"]) is not int or scenario["scenario_version"] != 1
            or type(scenario["steps"]) is not list or not 1 <= len(scenario["steps"]) <= 1000):
        raise ValidationError("scenario", "$", "Invalid scenario header or step count")
    checked = 0
    for index, step in enumerate(scenario["steps"]):
        if type(step) is not dict:
            raise ValidationError("scenario", "$", "Expected step object")
        kind = step.get("op")
        if type(kind) is not str or kind not in ("press", "advance", "enter_shell", "exit_shell"):
            raise ValidationError("scenario", "$", "Unsupported scenario operation")
        required = {"op", "at_ms", "widget_id"} if kind == "press" else {"op", "at_ms"}
        if (not required <= set(step) or set(step) - required - {"expect"}
                or type(step["at_ms"]) is not int or step["at_ms"] < 0
                or (kind == "press" and type(step["widget_id"]) is not str)
                or ("expect" in step and (type(step["expect"]) is not dict or not step["expect"]))):
            raise ValidationError("scenario", "$", "Invalid scenario step fields")
        if kind == "press":
            outcome = runtime.press(step["widget_id"], step["at_ms"], runtime.event_token())
            if outcome == "rejected":
                raise AssertionError("Scenario press was rejected at step {}".format(index))
        else:
            getattr(runtime, kind)(step["at_ms"])
        if runtime.errors:
            raise AssertionError("Runtime error at step {}".format(index))
        if "expect" in step:
            _expect(runtime.snapshot(), step["expect"])
            checked += 1
    if checked == 0:
        raise ValidationError("scenario", "$", "Scenario requires an explicit expected outcome")
    return {"steps": len(scenario["steps"]), "checkpoints": checked, "passed": True}
