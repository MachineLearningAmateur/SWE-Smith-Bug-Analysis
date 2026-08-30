#!/usr/bin/env python3
"""Estimate the NEUTRAL environment mix of the AIDev corpus (section 15).

    python scripts/profile_aidev_environment_mix.py --aidev-repo "D:/Code Projects/Algoverse/SSR_AIDev_Coverage"

Writes data/sampling/aidev_environment_profile.json.

What this reads: repository names, and the file extensions inside each case's
pull-request diff. From those it derives a language distribution.

What this refuses to read: every failure label, family, pattern, scope,
confidence and reviewer verdict in the AIDev repository. Those are named in
FORBIDDEN_SOURCES below and the script fails if it is pointed at one. The
handoff is explicit that AIDev failure-family frequencies and failure examples
must not influence SSR generation or sample selection; only neutral
environment characteristics may cross over.

Repository size is not recorded in the frozen AIDev evidence packets, so the
profile reports repo_size_bin as UNKNOWN and says so. Do not guess it from
diff size: a large diff in a small repository and a small diff in a large one
are both common, and a fabricated size bin would silently bias the SSR
environment match.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.paths import SAMPLING, ensure_dirs  # noqa: E402
from ssr.util import SsrError, read_json, setup_logging, sha256_json, utc_now, write_json  # noqa: E402

FORBIDDEN_SOURCES = (
    "review_results.jsonl",
    "reviews/",
    "analysis/dual_review",
    "analysis/taxonomy",
    "pattern_family",
    "agreement_metrics",
)

EXTENSION_LANGUAGE = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".m": "objective-c",
}

# Files that say nothing about the project's language.
NEUTRAL_EXTENSIONS = {".md", ".txt", ".json", ".yml", ".yaml", ".lock", ".toml", ".cfg", ".ini", ""}

_DIFF_FILE = re.compile(r"^diff --git a/.+? b/(.+)$", re.MULTILINE)


def case_language(diff_text: str) -> str:
    """Dominant source language of one case, by changed-file extension."""
    counts: Counter[str] = Counter()
    for match in _DIFF_FILE.finditer(diff_text.replace("\r\n", "\n")):
        suffix = Path(match.group(1)).suffix.lower()
        if suffix in NEUTRAL_EXTENSIONS:
            continue
        language = EXTENSION_LANGUAGE.get(suffix)
        if language:
            counts[language] += 1
    if not counts:
        return "unknown"
    top = counts.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        # A genuine tie is not a dominant language; say so rather than guess.
        return "unknown"
    return top[0][0]


def strict_case_ids(repo_root: Path) -> tuple[list[str], str]:
    """Case IDs of the strict AIDev corpus, if pandas can read the parquet."""
    parquet = repo_root / "data" / "derived" / "aidev_rq1_primary_cases.parquet"
    if not parquet.is_file():
        return [], "parquet_missing"
    try:
        import pandas as pd
    except ImportError:
        return [], "pandas_not_installed"
    frame = pd.read_parquet(parquet)
    column = "case_id" if "case_id" in frame.columns else frame.columns[0]
    return sorted(str(value).zfill(3) for value in frame[column].tolist()), "strict_corpus"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aidev-repo", required=True, help="path to a checkout of AIBugAnalysis")
    parser.add_argument(
        "--frame",
        choices=["strict", "all"],
        default="strict",
        help="strict: the RQ1 primary corpus if readable; all: every evidence packet",
    )
    parser.add_argument("--output", default=str(SAMPLING / "aidev_environment_profile.json"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    log = setup_logging(args.verbose)

    repo_root = Path(args.aidev_repo).resolve()
    if not repo_root.is_dir():
        raise SsrError(f"{repo_root} is not a directory")
    packets_dir = repo_root / "data" / "evidence_packets"
    if not packets_dir.is_dir():
        raise SsrError(f"{packets_dir} does not exist; is this an AIBugAnalysis checkout?")

    case_ids: list[str] = []
    frame_note = "all_evidence_packets"
    if args.frame == "strict":
        case_ids, frame_note = strict_case_ids(repo_root)
        if not case_ids:
            log.warning("strict corpus unavailable (%s); falling back to every packet", frame_note)
            frame_note = f"all_evidence_packets (strict unavailable: {frame_note})"

    packet_paths = sorted(packets_dir.glob("*.json"))
    if case_ids:
        wanted = set(case_ids)
        packet_paths = [path for path in packet_paths if path.stem in wanted]
    if not packet_paths:
        raise SsrError("no evidence packets matched the requested frame")

    languages: Counter[str] = Counter()
    repos: Counter[str] = Counter()
    per_case: list[dict] = []

    for path in packet_paths:
        for forbidden in FORBIDDEN_SOURCES:
            if forbidden in path.as_posix():
                raise SsrError(f"refusing to read a review artifact: {path}")
        packet = read_json(path)
        diff = (packet.get("pr_diff") or {}).get("content") or ""
        language = case_language(diff)
        repo = str(packet.get("repo") or "unknown")
        languages[language] += 1
        repos[repo] += 1
        per_case.append({"case_id": packet.get("case_id"), "repo": repo, "language": language})

    total = sum(languages.values())
    profile = {
        "generated_at_utc": utc_now(),
        "source_repository": "MachineLearningAmateur/AIBugAnalysis",
        "source_checkout": str(repo_root),
        "frame": frame_note,
        "cases": total,
        "unique_repositories": len(repos),
        "language_distribution": dict(languages.most_common()),
        "language_proportions": {
            name: round(count / total, 4) for name, count in languages.most_common()
        },
        "dominant_language": languages.most_common(1)[0][0] if languages else "unknown",
        "repo_size_bin_distribution": {"UNKNOWN": total},
        "repo_size_note": (
            "Repository size is not recorded in the frozen AIDev evidence packets and was "
            "not inferred. Any SSR environment match is therefore on language only; the "
            "repo-size mismatch is documented in docs/fidelity_limitations.md."
        ),
        "project_type_note": (
            "Project type is not deterministically available from the frozen packets and "
            "was not assigned."
        ),
        "repositories": dict(repos.most_common()),
        "per_case": per_case,
        "method": (
            "Language is the dominant source-file extension in each case's pull-request "
            "diff. Documentation, configuration and lock files are ignored. A tie gives "
            "'unknown' rather than a guess."
        ),
        "isolation_statement": (
            "Only repository names and diff file extensions were read. No failure label, "
            "family, pattern, scope, confidence or reviewer verdict was read or used."
        ),
    }
    profile["profile_sha256"] = sha256_json(
        {key: value for key, value in profile.items() if key != "generated_at_utc"}
    )
    write_json(Path(args.output), profile)

    log.info("profiled %d case(s) across %d repositories", total, len(repos))
    print(json.dumps({
        "output": args.output,
        "frame": frame_note,
        "cases": total,
        "language_proportions": profile["language_proportions"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
