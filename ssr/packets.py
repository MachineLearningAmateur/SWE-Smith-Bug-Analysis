"""Reconstruction of SWE-smith tasks, and the neutral review packets.

## The clean state

**The clean state is the parent of the ``Bug Patch`` commit. It is NOT the
dataset's ``base_commit`` field.**

This is not a stylistic preference. It was verified by reconstruction on five
instances spanning five generation methods: ``base_commit`` has a different
tree from the bug's actual parent in every case, and the bug diff does not
apply to it. A packet built on ``base_commit`` would show the reviewer a diff
against the wrong code. ``scripts/verify_swesmith_semantics.py`` re-checks
this, and ``tests/test_swesmith_packets.py`` fails if the rule is ever
reintroduced the wrong way round.

Each task is a branch in a SWE-smith mirror repository with three commits,
built by ``swesmith/harness/gather.py``::

    Remove F2P Tests     branch head: what the agent is given
    Bug Patch            the buggy state
    Initial commit       the CLEAN state

## The patch direction

**The dataset ``patch`` field is the BUG INJECTION, not a repair.** It is
byte-equal to the ``Bug Patch`` commit's own diff. The reference repair is its
REVERSE, and there is no separate field for it. Calling ``patch`` a repair
patch would invert the whole study.

## What a packet may contain

Enough to classify the synthetic bug, and nothing about how it was made:

    BUG_DIFF          the bug injection diff
    CODE_CONTEXT_NN   the touched files as they stand in the buggy state
    SPECIFICATION     the task's problem statement
    TEST_FAILURE_NN   the officially validated failing tests
    REFERENCE_REPAIR  the reverse of the bug diff

Withheld: generation method, trajectory identity or text, source model,
whether a task was attempted more than once, population frequencies, the
mirror repository name, the instance ID (which encodes the method), and every
AIDev label or frequency.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from ssr.util import SsrError, sha256_text, write_json, write_text

REVIEWER_QUESTION = (
    "Based only on the frozen evidence in this packet, what kind of technical "
    "failure does this synthetic buggy repository state represent?"
)

BUG_COMMIT_SUBJECT = "Bug Patch"
MIRROR_URL = "https://github.com/{repo}.git"

# Terms that must not appear in a field the harness itself wrote. The
# reviewer is told which corpus they are reviewing; what must stay hidden is
# how each individual bug was made and which trajectory it produced.
#
# The case ID is exempt: "SWESMITH_042" is this study's own neutral
# identifier, mandated by the protocol, and it says nothing about the bug.
METADATA_FORBIDDEN = (
    "swesmith/",
    "swe-smith",
    "trajectory",
    "traj_id",
    "swe-agent",
    "aidev",
    "generation_method",
    "method_family",
    "lm_rewrite",
    "lm_modify",
    "func_pm_",
    "func_basic",
    "combine_file",
    "combine_module",
    "pr_mirror",
)

# Evidence files hold real source code and real diffs. Scanning them for
# English or programming words would reject sound packets: `instance_id` and
# `trajectory` are ordinary identifiers, and a project may own a module
# called `combine_file.py`. So the body scan looks for the LITERAL values
# that identify this task instead, which cannot occur by accident.
def body_terms(instance_id: str, mirror_repo: str) -> tuple[str, ...]:
    """The exact strings that would identify how this bug was made."""
    method = instance_id.rpartition(".")[2]
    return tuple(term.lower() for term in (instance_id, mirror_repo, method) if term)

# Packet fields whose value is copied out of the repository or the upstream
# project: a source path, a test node ID, an upstream project name.
REPOSITORY_DERIVED_KEYS = frozenset({"test_name", "test_file", "repo_path", "name", "path"})


@dataclass
class LeakageFinding:
    where: str
    term: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.where}: forbidden term {self.term!r} near {self.excerpt!r}"


def _scan(text: str, where: str, terms: tuple[str, ...]) -> list[LeakageFinding]:
    lowered = text.lower()
    findings = []
    for term in terms:
        position = lowered.find(term)
        if position >= 0:
            start = max(0, position - 30)
            findings.append(LeakageFinding(where, term, text[start : position + len(term) + 30]))
    return findings


def _without(text: str, allow: tuple[str, ...]) -> str:
    """Blank out strings the packet is entitled to contain, such as its own
    case ID, before scanning what is left."""
    for literal in allow:
        if literal:
            text = re.sub(re.escape(literal), " ", text, flags=re.IGNORECASE)
    return text


def scan_metadata(payload: Any, *, path: str = "packet.json",
                  allow: tuple[str, ...] = ()) -> list[LeakageFinding]:
    findings: list[LeakageFinding] = []

    def walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                findings.extend(_scan(_without(str(key), allow), f"{trail}.{key} (key)", METADATA_FORBIDDEN))
                walk(value, f"{trail}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                walk(value, f"{trail}[{index}]")
        elif isinstance(node, str):
            findings.extend(_scan(_without(node, allow), trail, METADATA_FORBIDDEN))

    walk(payload, path)
    return findings


def scan_body(text: str, *, where: str, terms: tuple[str, ...]) -> list[LeakageFinding]:
    """Scan an evidence file for the literals that identify this task."""
    return _scan(text, where, terms)


def scan_filenames(names: Iterable[str], *, allow: tuple[str, ...] = ()) -> list[LeakageFinding]:
    findings: list[LeakageFinding] = []
    for name in names:
        findings.extend(_scan(_without(name, allow), f"filename {name}", METADATA_FORBIDDEN))
    return findings


# --------------------------------------------------------------------------
# reconstruction
# --------------------------------------------------------------------------
@dataclass
class Reconstruction:
    """A task rebuilt from its mirror repository."""

    instance_id: str
    clean_commit: str
    bug_commit: str
    bug_diff: str
    reference_repair: str
    code_context: dict[str, str]
    checks: dict[str, str] = field(default_factory=dict)
    failure: str | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None


def _git(*args: str, cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """Run git, decoding as UTF-8 with replacement.

    ``text=True`` decodes with the locale encoding, which on Windows is
    cp1252 and raises on the first non-ASCII byte in a diff. Source files
    legitimately contain non-ASCII, so the encoding is pinned here rather
    than left to the machine.
    """
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, timeout=timeout
    )
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        (result.stdout or b"").decode("utf-8", "replace"),
        (result.stderr or b"").decode("utf-8", "replace"),
    )


def _normalise_diff(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line.startswith("index ") and line.strip()]


_DIFF_FILE = re.compile(r"^diff --git a/.+? b/(.+)$", re.MULTILINE)


def touched_files(diff_text: str) -> list[str]:
    return sorted({m.group(1) for m in _DIFF_FILE.finditer(diff_text.replace("\r\n", "\n"))})


def reconstruct(task: dict[str, Any], workdir: Path, *, max_context_bytes: int = 160_000) -> Reconstruction:
    """Rebuild one task from its mirror repository.

    Returns a Reconstruction whose ``failure`` is set when any link of the
    chain does not hold. A failure is never patched over: the instance is
    excluded and the sampler re-run.
    """
    instance_id = task["instance_id"]
    repo = task["repo"]
    checks: dict[str, str] = {}

    def bail(reason: str) -> Reconstruction:
        return Reconstruction(instance_id, "", "", "", "", {}, checks, failure=reason)

    clone = workdir / instance_id[-60:].replace("/", "_")
    clone.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", ".", cwd=clone)
    _git("remote", "add", "origin", MIRROR_URL.format(repo=repo), cwd=clone)

    fetched = _git("fetch", "-q", "--depth", "3", "origin", instance_id, cwd=clone)
    if fetched.returncode != 0:
        return bail(f"branch not fetchable: {fetched.stderr.strip()[:200]}")

    history = [l for l in _git("log", "--format=%H%x09%s", "FETCH_HEAD", cwd=clone).stdout.splitlines() if l.strip()]
    bug_commits = [l.split("\t")[0] for l in history if l.split("\t")[-1] == BUG_COMMIT_SUBJECT]
    if not bug_commits:
        return bail(f"no {BUG_COMMIT_SUBJECT!r} commit on the branch")
    bug_commit = bug_commits[0]

    parent = _git("rev-parse", f"{bug_commit}^", cwd=clone).stdout.strip()
    if not parent:
        return bail("the bug commit has no parent, so there is no clean state")
    checks["clean_state"] = f"parent of the bug commit ({parent[:12]}), NOT base_commit"

    # The dataset patch must be the forward transformation from that parent.
    patch_file = clone / ".packet_patch.diff"
    patch_file.write_text(task["patch"], encoding="utf-8", newline="\n")
    _git("checkout", "-q", parent, cwd=clone)
    applies = _git("apply", "--check", str(patch_file), cwd=clone)
    if applies.returncode != 0:
        return bail(f"the bug diff does not apply to the clean state: {applies.stderr.strip()[:200]}")
    checks["patch_applies_to_clean"] = "the dataset patch is the clean -> buggy transformation"

    own_result = _git("diff", parent, bug_commit, cwd=clone)
    if own_result.returncode != 0:
        return bail(f"cannot diff the bug commit: {own_result.stderr.strip()[:200]}")
    own = own_result.stdout
    if _normalise_diff(own) != _normalise_diff(task["patch"] or ""):
        return bail("the dataset patch is not the bug commit's own diff")
    checks["patch_equals_bug_commit"] = "byte-equal to the bug commit's diff, ignoring index lines"

    # The reference repair is the REVERSE of the bug diff. Taken as a real
    # diff rather than by flipping text, so it applies cleanly.
    repair_result = _git("diff", bug_commit, parent, cwd=clone)
    reference_repair = repair_result.stdout
    if repair_result.returncode != 0 or not reference_repair.strip():
        return bail("the reverse diff is empty")
    checks["reference_repair"] = "the reverse of the bug diff, taken from git"

    # Code context is the BUGGY state: that is the state under review.
    _git("checkout", "-q", "-f", bug_commit, cwd=clone)
    context: dict[str, str] = {}
    for path in touched_files(task["patch"]):
        target = clone / path
        if target.is_file():
            try:
                context[path] = target.read_text(encoding="utf-8", errors="replace")[:max_context_bytes]
            except OSError:
                continue
    if not context:
        return bail("no touched file could be read from the buggy state")
    checks["code_context"] = f"{len(context)} file(s) read from the buggy state"

    return Reconstruction(
        instance_id=instance_id,
        clean_commit=parent,
        bug_commit=bug_commit,
        bug_diff=task["patch"],
        reference_repair=reference_repair,
        code_context=context,
        checks=checks,
    )


# --------------------------------------------------------------------------
# packet building
# --------------------------------------------------------------------------
@dataclass
class PacketSource:
    case_id: str
    upstream_repo: str
    language: str
    reconstruction: Reconstruction
    problem_statement: str
    fail_to_pass: list[str]
    pass_to_pass_count: int
    mirror_repo: str = ""


def _safe_name(repo_path: str) -> str:
    name = PurePosixPath(repo_path.replace("\\", "/")).name or "file"
    return re.sub(r"[^A-Za-z0-9_.\-]", "_", name)[:80] or "file"


def _diff_stats(diff_text: str) -> tuple[int, int, int]:
    added = deleted = 0
    for line in diff_text.replace("\r\n", "\n").split("\n"):
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted, len(touched_files(diff_text))


TEST_EVIDENCE_HEADER = """\
# Failing test evidence

The following tests **pass on the working state and fail on this buggy state**.
They come from the corpus's own execution validation; they were not re-run
here.

The test files themselves are not present in the repository state under
review: they were removed when the task was built, so the bug must be judged
from the code, not from reading the assertions.

Failing tests ({n_fail}):

{failing}

Tests passing in both states: {n_pass}
"""


class PacketBuilder:
    def __init__(self, root: Path, *, max_oracle: int = 20, max_context: int = 12):
        self.root = Path(root)
        self.max_oracle = max_oracle
        self.max_context = max_context

    def build(self, source: PacketSource) -> dict[str, Any]:
        directory = self.root / source.case_id
        directory.mkdir(parents=True, exist_ok=True)
        recon = source.reconstruction
        written: dict[str, str] = {}
        findings: list[LeakageFinding] = []
        # The literals that would identify how this bug was made.
        leak_terms = body_terms(recon.instance_id, source.mirror_repo)
        allow = (source.case_id,)

        # -- the bug ------------------------------------------------------
        bug_sha = write_text(directory / "bug_diff.diff", recon.bug_diff)
        written["bug_diff.diff"] = bug_sha
        findings += scan_body(recon.bug_diff, where="bug_diff.diff", terms=leak_terms)
        added, deleted, files_changed = _diff_stats(recon.bug_diff)

        # -- the reference repair ------------------------------------------
        repair_sha = write_text(directory / "reference_repair.diff", recon.reference_repair)
        written["reference_repair.diff"] = repair_sha
        findings += scan_body(recon.reference_repair, where="reference_repair.diff", terms=leak_terms)

        # -- code context ---------------------------------------------------
        context_entries = []
        for index, (repo_path, text) in enumerate(sorted(recon.code_context.items())[: self.max_context], start=1):
            name = f"context/{index:02d}_{_safe_name(repo_path)}"
            sha = write_text(directory / name, text)
            written[name] = sha
            findings += scan_body(text, where=name, terms=leak_terms)
            context_entries.append({
                "evidence_id": f"CODE_CONTEXT_{index:02d}",
                "path": name,
                "repo_path": repo_path.replace("\\", "/"),
                "sha256": sha,
            })

        # -- specification --------------------------------------------------
        spec = (source.problem_statement or "").strip() or "(no specification was provided with this task)"
        spec_sha = write_text(directory / "specification.md", spec + "\n")
        written["specification.md"] = spec_sha
        findings += scan_body(spec, where="specification.md", terms=leak_terms)

        # -- failing tests ---------------------------------------------------
        failing = [t.replace("\\", "/") for t in sorted(source.fail_to_pass)]
        shown = failing[: self.max_oracle]
        evidence = TEST_EVIDENCE_HEADER.format(
            n_fail=len(failing),
            failing="\n".join(f"  {name}" for name in shown)
            + ("\n  ... and %d more" % (len(failing) - len(shown)) if len(failing) > len(shown) else ""),
            n_pass=source.pass_to_pass_count,
        )
        tests_sha = write_text(directory / "test_evidence.md", evidence)
        written["test_evidence.md"] = tests_sha
        test_entries = [
            {"evidence_id": f"TEST_FAILURE_{index:02d}", "test_name": name,
             "test_file": name.split("::")[0] if "::" in name else None}
            for index, name in enumerate(shown, start=1)
        ]
        if not test_entries:
            raise SsrError(f"{source.case_id}: a packet needs at least one failing test")

        evidence_ids = (
            ["BUG_DIFF", "REFERENCE_REPAIR", "SPECIFICATION"]
            + [e["evidence_id"] for e in context_entries]
            + [e["evidence_id"] for e in test_entries]
        )

        packet = {
            "case_id": source.case_id,
            "packet_version": 2,
            "repository": {
                "name": source.upstream_repo,
                "language": source.language,
            },
            "bug_diff": {
                "evidence_id": "BUG_DIFF",
                "path": "bug_diff.diff",
                "sha256": bug_sha,
                "files_changed": files_changed,
                "lines_added": added,
                "lines_deleted": deleted,
                "description": "The change that introduced the defect, applied to the working code.",
            },
            "reference_repair": {
                "evidence_id": "REFERENCE_REPAIR",
                "path": "reference_repair.diff",
                "sha256": repair_sha,
                "description": "The reverse of the bug diff: it restores the working code.",
            },
            "specification": {
                "evidence_id": "SPECIFICATION",
                "path": "specification.md",
                "sha256": spec_sha,
                "description": "The issue text supplied with this task. A description of the "
                               "defect, not independent evidence of it; it may be inaccurate.",
            },
            "code_context": context_entries,
            "failing_tests": {
                "evidence_id_prefix": "TEST_FAILURE",
                "path": "test_evidence.md",
                "sha256": tests_sha,
                "failing_count": len(failing),
                "passing_count": source.pass_to_pass_count,
                "tests": test_entries,
            },
            "evidence_ids": sorted(set(evidence_ids)),
            "reviewer_question": REVIEWER_QUESTION,
        }

        findings += scan_metadata(packet, allow=allow)
        findings += scan_filenames(list(written) + [source.case_id], allow=allow)
        if findings:
            raise SsrError(
                f"{source.case_id}: leakage scan failed, packet not published:\n  "
                + "\n  ".join(str(f) for f in findings[:20])
            )

        written["packet.json"] = write_json(directory / "packet.json", packet)
        return {"packet": packet, "files": written, "directory": str(directory)}


def packet_file_hashes(directory: Path) -> dict[str, str]:
    from ssr.util import sha256_file

    directory = Path(directory)
    return {
        path.relative_to(directory).as_posix(): sha256_file(path)
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


def packet_digest(directory: Path) -> str:
    hashes = packet_file_hashes(directory)
    return sha256_text("\n".join(f"{k}:{v}" for k, v in sorted(hashes.items())))
