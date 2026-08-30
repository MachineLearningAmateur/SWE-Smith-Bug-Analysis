"""The environment registry.

``configs/environments.yaml`` names the SWE-smith environments a corpus run
may draw from, plus the harness-proving entries under ``smoke_environments``.
Smoke entries are kept in a separate key so that a corpus run cannot select
one by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ssr.config import load_config
from ssr.exec_env import ExecutionEnvironment, make_environment
from ssr.paths import workspace_root
from ssr.util import SsrError


@dataclass
class EnvironmentEntry:
    name: str
    spec: dict[str, Any]
    is_smoke: bool

    @property
    def backend(self) -> str:
        return str(self.spec.get("backend", "docker"))

    @property
    def upstream(self) -> str:
        upstream = self.spec.get("upstream")
        if not upstream:
            raise SsrError(
                f"environment {self.name!r} has no 'upstream'. The neutral upstream "
                "project name is required: review packets must never carry the "
                "SWE-smith image name."
            )
        return str(upstream)

    @property
    def language(self) -> str:
        return str(self.spec.get("language", "unknown"))

    def build(self) -> ExecutionEnvironment:
        spec = dict(self.spec)
        spec.pop("upstream", None)
        spec.pop("notes", None)
        spec.pop("language", None)
        if "repo_path" in spec:
            spec["repo_path"] = str(spec["repo_path"]).replace(
                "{workspace}", workspace_root().as_posix()
            )
        return make_environment(spec)


def load_registry() -> dict[str, EnvironmentEntry]:
    config = load_config("environments")
    entries: dict[str, EnvironmentEntry] = {}
    for name, spec in (config.get("environments") or {}).items():
        entries[name] = EnvironmentEntry(name=name, spec=dict(spec), is_smoke=False)
    for name, spec in (config.get("smoke_environments") or {}).items():
        if name in entries:
            raise SsrError(f"environment {name!r} is declared twice")
        entries[name] = EnvironmentEntry(name=name, spec=dict(spec), is_smoke=True)
    return entries


def get_environment(name: str, *, allow_smoke: bool = False) -> EnvironmentEntry:
    registry = load_registry()
    if name not in registry:
        known = ", ".join(sorted(registry)) or "(the registry is empty)"
        raise SsrError(f"unknown environment {name!r}. Declared environments: {known}")
    entry = registry[name]
    if entry.is_smoke and not allow_smoke:
        raise SsrError(
            f"environment {name!r} is a harness-proving entry, not a corpus environment. "
            "Pass --allow-smoke to use it, and remember that candidates produced this way "
            "are excluded from the pool."
        )
    return entry


def corpus_environments() -> list[EnvironmentEntry]:
    return [entry for entry in load_registry().values() if not entry.is_smoke]
