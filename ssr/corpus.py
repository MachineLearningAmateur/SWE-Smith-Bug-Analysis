"""The corpus status record.

``data/CORPUS_STATUS.json`` answers one question for anyone who opens this
checkout: **are these 100 packets the real research corpus, or a rehearsal?**

It matters because the review workflow is identical either way. Without a
marker, a rehearsal run would produce agreement statistics that look exactly
like results. The marker travels with the packets, is recorded in each
reviewer's metadata, and is printed by the analysis scripts.

The record is reviewer-visible, so it carries no generation information: no
model identity, no strategy counts, no backend names, no allocation. Only
whether the corpus is real, how many packets there are, and the hashes that
tie the packets, the manifest and the taxonomy together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ssr import PROTOCOL_VERSION, __version__
from ssr.paths import CORPUS_STATUS, REVIEW_MANIFEST, REVIEW_SNAPSHOT_MANIFEST
from ssr.taxonomy import taxonomy_fingerprint
from ssr.util import SsrError, read_json, sha256_file, utc_now, write_json

RESEARCH = "RESEARCH"
REHEARSAL = "REHEARSAL"

REHEARSAL_NOTE = (
    "REHEARSAL CORPUS. These packets were not produced by a validated research "
    "run: at least one of them came from a harness-proving or synthetic source. "
    "Any agreement statistic computed from a review of this corpus is a test of "
    "the workflow, NOT a research result. Do not report it."
)

RESEARCH_NOTE = (
    "Research corpus. Every packet came from an execution-validated bug state "
    "produced in an isolated environment by the configured model."
)


@dataclass
class CorpusStatus:
    corpus_kind: str
    packet_count: int
    taxonomy_fingerprint: str
    snapshot_manifest_sha256: str
    review_manifest_sha256: str
    built_at_utc: str
    harness_version: str
    protocol_version: str
    note: str

    @property
    def is_research(self) -> bool:
        return self.corpus_kind == RESEARCH

    def to_dict(self) -> dict[str, Any]:
        return {
            "corpus_kind": self.corpus_kind,
            "packet_count": self.packet_count,
            "taxonomy_fingerprint": self.taxonomy_fingerprint,
            "snapshot_manifest_sha256": self.snapshot_manifest_sha256,
            "review_manifest_sha256": self.review_manifest_sha256,
            "built_at_utc": self.built_at_utc,
            "harness_version": self.harness_version,
            "protocol_version": self.protocol_version,
            "note": self.note,
        }


def classify(entries: Iterable[Any]) -> tuple[str, list[str]]:
    """Decide RESEARCH or REHEARSAL from the pool entries behind the packets.

    Anything that did not come from an isolated environment run by the real
    model makes the whole corpus a rehearsal. One rehearsal packet in a
    hundred is enough: the sample is the unit, not the packet.
    """
    reasons: list[str] = []
    for entry in entries:
        if getattr(entry, "scripted", False):
            reasons.append(f"{entry.bug_id}: generated with a scripted or synthetic model")
        backend = getattr(entry, "backend", "unknown")
        if backend != "docker":
            reasons.append(f"{entry.bug_id}: built on the {backend!r} backend, which is not isolated")
    return (REHEARSAL if reasons else RESEARCH), sorted(set(reasons))


def write_status(corpus_kind: str, packet_count: int) -> CorpusStatus:
    status = CorpusStatus(
        corpus_kind=corpus_kind,
        packet_count=packet_count,
        taxonomy_fingerprint=taxonomy_fingerprint(),
        snapshot_manifest_sha256=sha256_file(REVIEW_SNAPSHOT_MANIFEST),
        review_manifest_sha256=sha256_file(REVIEW_MANIFEST) if REVIEW_MANIFEST.is_file() else "",
        built_at_utc=utc_now(),
        harness_version=__version__,
        protocol_version=PROTOCOL_VERSION,
        note=RESEARCH_NOTE if corpus_kind == RESEARCH else REHEARSAL_NOTE,
    )
    write_json(CORPUS_STATUS, status.to_dict())
    return status


def read_status() -> CorpusStatus:
    if not CORPUS_STATUS.is_file():
        raise SsrError(
            f"{CORPUS_STATUS} does not exist. This checkout has no corpus. Build the "
            "review packets, or obtain a checkout that already has them."
        )
    record = read_json(CORPUS_STATUS)
    try:
        return CorpusStatus(**{key: record[key] for key in CorpusStatus.__annotations__})
    except KeyError as exc:
        raise SsrError(f"{CORPUS_STATUS} is missing {exc}") from exc


def status_banner() -> str:
    """One line for the top of any report. Loud when the corpus is a rehearsal."""
    try:
        status = read_status()
    except SsrError:
        return "corpus status: UNKNOWN (data/CORPUS_STATUS.json is absent)"
    if status.is_research:
        return f"corpus status: RESEARCH, {status.packet_count} packet(s)"
    return (
        f"!! corpus status: REHEARSAL, {status.packet_count} packet(s). "
        "These numbers are a workflow test, not a research result. !!"
    )
