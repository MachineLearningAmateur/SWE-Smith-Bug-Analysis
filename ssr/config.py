"""Configuration loading.

Every script takes its knobs from ``configs/*.yaml`` so that a run is
reproducible from the repository state alone. Command-line flags may only
narrow what runs (which bug, how many), never change a recorded parameter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ssr.paths import CONFIGS
from ssr.util import SsrError, sha256_file


class Config(dict):
    """A dict that reports a helpful path when a key is missing."""

    def __init__(self, data: dict, source: Path):
        super().__init__(data)
        self.source = source
        self.sha256 = sha256_file(source)

    def require(self, dotted: str) -> Any:
        node: Any = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                raise SsrError(f"{self.source.name}: missing required key {dotted!r}")
            node = node[part]
        return node

    def get_path(self, dotted: str, default: Any = None) -> Any:
        node: Any = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def load_config(name: str) -> Config:
    """Load ``configs/<name>.yaml``."""
    path = CONFIGS / f"{name}.yaml" if not name.endswith(".yaml") else CONFIGS / name
    if not path.is_file():
        raise SsrError(f"config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SsrError(f"config {path} must be a YAML mapping")
    return Config(data, path)


def config_fingerprint(*names: str) -> dict[str, str]:
    """SHA-256 of each named config, for the run record."""
    return {name: load_config(name).sha256 for name in names}


def resolve_repo_file(relative: str) -> Path:
    from ssr.paths import REPO_ROOT

    path = (REPO_ROOT / relative).resolve()
    if not path.is_file():
        raise SsrError(f"file referenced by config does not exist: {relative}")
    return path
