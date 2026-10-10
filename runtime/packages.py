"""Version dispatch for exact package validation; never executes app source."""

from runtime import program, validation


def package_report(raw):
    # Both currently deployed envelopes have the same byte/depth ceiling. The
    # schema2 decoder is strict about JSON; the selected validator owns semantics.
    value = program.decode(raw)
    if type(value) is dict and type(value.get("schema_version")) is int and value["schema_version"] == 2:
        return program.program_report(raw)
    return validation.package_report(raw)
