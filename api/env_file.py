
"""Load local settings from the repository's .env file.

Variables already set in the environment always win, so a server's
service configuration is never overridden by a stray file. Empty
values are skipped and therefore count as not configured.
"""

import os
from pathlib import Path


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env_file(path=ENV_FILE):
    """Set NAME=value lines from the file; return the names set."""

    path = Path(path)

    if not path.is_file():
        return []

    loaded = []
    # utf-8-sig tolerates the byte-order mark Notepad may add.
    lines = path.read_text(encoding="utf-8-sig").splitlines()

    for number, raw in enumerate(lines, start=1):
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export "):].lstrip()

        name, separator, value = line.partition("=")
        name = name.strip()
        value = value.strip()

        if not separator or not name.isidentifier():
            # Never echo the line: it may contain a secret.
            raise ValueError(
                f"{path.name} line {number}: expected NAME=value"
            )

        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        if value and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)

    return loaded
