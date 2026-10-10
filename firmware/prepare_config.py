"""Apply reviewed board defaults without printing or replacing private values."""
import os
import re
import sys
import tempfile
from pathlib import Path


def prepare(config: Path, defaults: Path) -> None:
    assignments = {}
    for line in defaults.read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            assignments[line.split("=", 1)[0]] = line
    original = config.read_text().splitlines() if config.exists() else []
    preserved = []
    for line in original:
        match = re.match(r"(?:# )?(CONFIG_[A-Z0-9_]+)(?:=| is not set)", line)
        if not match or match[1] not in assignments:
            preserved.append(line)
    data = "\n".join(preserved + list(assignments.values())) + "\n"
    fd, name = tempfile.mkstemp(prefix=".sdkconfig-", dir=config.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, config)
    finally:
        if os.path.exists(name):
            os.unlink(name)


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
