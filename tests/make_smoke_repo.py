#!/usr/bin/env python3
"""Build a tiny git repository for proving the harness end to end.

    python tests/make_smoke_repo.py

Creates the repository named by ``smoke_environments.local_smoke`` in
configs/environments.yaml: a small Python package with a pytest suite and a
short commit history, so that both generation strategies have something to
work with.

This repository is NOT a research artifact. Bugs generated against it run on
the local backend, which is not isolated, and ssr/pool.py drops local-backend
candidates from the sampling frame.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.paths import workspace_root  # noqa: E402
from ssr.util import force_rmtree, write_text  # noqa: E402

CORE_V1 = '''\
"""Numeric helpers."""


def clamp(value, low, high):
    if value < low:
        return low
    return value


def normalise(values):
    total = sum(values)
    if total == 0:
        return [0.0 for _ in values]
    return [value / total for value in values]


def running_mean(values, window):
    if window <= 0:
        raise ValueError("window must be positive")
    out = []
    for index in range(len(values)):
        start = max(0, index - window + 1)
        chunk = values[start : index + 1]
        out.append(sum(chunk) / len(chunk))
    return out
'''

CORE_V2 = '''\
"""Numeric helpers."""


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def normalise(values):
    total = sum(values)
    if total == 0:
        return [0.0 for _ in values]
    return [value / total for value in values]


def running_mean(values, window):
    if window <= 0:
        raise ValueError("window must be positive")
    out = []
    for index in range(len(values)):
        start = max(0, index - window + 1)
        chunk = values[start : index + 1]
        out.append(sum(chunk) / len(chunk))
    return out
'''

TESTS = '''\
from smokepkg.core import clamp, normalise, running_mean


def test_clamp_below():
    assert clamp(-5, 0, 10) == 0


def test_clamp_inside():
    assert clamp(4, 0, 10) == 4


def test_clamp_above():
    assert clamp(50, 0, 10) == 10


def test_normalise_sums_to_one():
    assert sum(normalise([1, 1, 2])) == 1.0


def test_normalise_all_zero():
    assert normalise([0, 0]) == [0.0, 0.0]


def test_running_mean_window_one():
    assert running_mean([1, 2, 3], 1) == [1.0, 2.0, 3.0]


def test_running_mean_window_two():
    assert running_mean([1, 3], 2) == [1.0, 2.0]


def test_running_mean_rejects_zero_window():
    try:
        running_mean([1], 0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
'''


GIT = shutil.which("git") or "git"


def run(*args: str, cwd: Path) -> None:
    """Call git directly.

    Not through a shell: a login shell can put a much older git first on
    PATH, and this script needs switches that old git does not have.
    """
    result = subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"failed: git {' '.join(args)}\n{result.stdout}\n{result.stderr}")


def main() -> int:
    root = workspace_root() / "smoke_repo"
    force_rmtree(root)
    root.mkdir(parents=True)

    write_text(root / "smokepkg" / "__init__.py", "from smokepkg.core import clamp  # noqa: F401\n")
    write_text(root / "smokepkg" / "core.py", CORE_V1)
    write_text(root / "tests" / "test_core.py", TESTS.replace("def test_clamp_above():\n    assert clamp(50, 0, 10) == 10\n\n\n", ""))
    write_text(root / "README.md", "# smokepkg\n\nA tiny package used to prove the SSR harness.\nRun the tests with pytest.\n")
    write_text(root / "pyproject.toml", '[project]\nname = "smokepkg"\nversion = "0.1.0"\n')

    run("init", "-q", cwd=root)
    run("symbolic-ref", "HEAD", "refs/heads/main", cwd=root)
    run("config", "user.email", "ssr@invalid", cwd=root)
    run("config", "user.name", "ssr", cwd=root)
    run("add", "-A", cwd=root)
    run("commit", "-q", "-m", "initial package", cwd=root)

    # A second commit that adds real behaviour, so HISTORY_REVERSION has a
    # meaningful commit to undo.
    write_text(root / "smokepkg" / "core.py", CORE_V2)
    write_text(root / "tests" / "test_core.py", TESTS)
    run("add", "-A", cwd=root)
    run("commit", "-q", "-m", "clamp: honour the upper bound", cwd=root)

    write_text(root / "docs.md", "clamp(value, low, high) limits value to the range [low, high].\n")
    run("add", "-A", cwd=root)
    run("commit", "-q", "-m", "document clamp", cwd=root)

    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
