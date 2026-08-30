# Quickstart

Two audiences, two paths. Pick yours.

---

## A. You are reviewing the 100 cases

You need **Python 3.10 or later** and nothing else. No Docker, no API key, no
network. A review reads frozen files and writes JSON.

### macOS and Linux

```bash
git clone <repository-url> ssr-review
cd ssr-review
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-review.txt
python scripts/check_review_ready.py --reviewer claude   # or codex
```

### Windows (PowerShell)

```powershell
git clone <repository-url> ssr-review
cd ssr-review
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-review.txt
python scripts\check_review_ready.py --reviewer claude   # or codex
```

### Windows (Git Bash) or WSL

Use the macOS and Linux commands above.

### What the check tells you

It prints one line per check, and ends either with the three steps to start,
or with what must be fixed. It verifies the Python version, the two packages,
the frozen taxonomy hashes, **whether the corpus is research or a rehearsal**,
and that every packet file still matches the hash it was frozen with.

If it says `corpus: FAIL ... this checkout has no corpus yet`, the 100 packets
have not been built and committed. Ask whoever gave you the checkout; there is
nothing to review until they land.

### Then

1. Read `taxonomy/frozen_failure_taxonomy_v1.md` in full, once.
2. Read `CLAUDE.md` (Claude) or `AGENTS.md` (Codex). They are the whole brief.
3. For each case, read only `data/review_packets/SWESMITH_nnn/` and save one file
   at `reviews/<you>/cases/SWESMITH_nnn.<ext>`. Save it **immediately**, one at a
   time. A session that dies mid-run must lose one case, not fifty.
4. Validate as you go:

   ```bash
   python scripts/validate_review_output.py --reviewer claude --case SWESMITH_007
   ```

5. When all 100 exist:

   ```bash
   python scripts/validate_review_output.py --reviewer claude --finalise
   ```

`--finalise` refuses if a case is missing, if a record breaks a frozen rule,
or if the evidence changed under you.

### Running Claude Code or Codex on it

Both read their instruction file from the repository root automatically:
Claude Code reads `CLAUDE.md`, Codex reads `AGENTS.md`. Those briefs are
self-contained — they carry the label definitions quoted from the frozen
taxonomy, every `failure_scope` and `taxonomy_fit` value, what a packet holds,
and a worked case — so the agent needs nothing else.

**Ready prompts to paste, and the two-branch isolation setup, are in
[`README.md`](README.md) under "Running the blind reviews".**

Codex writes JSON; Claude writes YAML. The records are semantically identical
and validate against the same schema. `scripts/check_review_ready.py` tells you
which format and file name your reviewer uses.

The project also ships `.claude/settings.json`, which denies Claude Code read
access to the hidden generation metadata, so an accidental peek fails rather
than lands.

---

## B. You are running the study

```bash
python -m pip install -e ".[dev]"
python -m pytest tests -q
python scripts/check_review_ready.py
```

The pipeline is in `README.md`. It needs no Docker and no API key: the bug
diffs and test lists come from pinned Hugging Face dataset revisions, and the
clean and buggy states from the public mirror repositories.

---

## C. You are sending the review to someone else

Hand them a bundle rather than the whole repository. A bundle contains the
packets, the taxonomy and the review tooling, and **physically excludes** the
generation metadata, the sampling crosswalk, the other reviewer's directory
and the analysis. Blindness stops being a rule they must follow and becomes a
fact about what they were given.

```bash
python scripts/make_review_bundle.py --reviewer codex --out ../codex_review --zip
```

The export verifies itself before reporting success: it re-hashes every packet
inside the bundle and refuses to publish one that contains excluded material.

When the review comes back:

```bash
python scripts/import_review_results.py --reviewer codex --from ../codex_review
```

The import refuses a review done against different evidence or a different
taxonomy version, so a stale bundle cannot be merged by accident.

---

## Reading the corpus marker

Every checkout carries `data/CORPUS_STATUS.json`, and every tool prints it:

* **RESEARCH** — every packet came from an execution-validated bug state built
  in an isolated environment by the configured model. Results may be reported.
* **REHEARSAL** — at least one packet came from a harness-proving or synthetic
  source. A review of it tests the workflow. **Its numbers are not results and
  must not be reported.**

The marker is written when the packets are built, copied into each reviewer's
metadata, and printed at the top of the family and comparison reports. It is
not something anyone has to remember.

---

## Troubleshooting

**`python: command not found` on macOS or Linux.** Use `python3`, or activate
the virtual environment shown above.

**`ModuleNotFoundError: No module named 'ssr'`.** Run the scripts from the
repository root. They add the root to the path themselves; running them from
elsewhere with a bare filename does not.

**`packet integrity: FAIL`.** A packet file changed after it was frozen. A
review against changed evidence is void. Restore it:
`git checkout -- data/review_packets`.

**Line endings.** `.gitattributes` turns conversion off for the whole
repository, because the frozen hashes are hashes of file bytes. Do not
override it, and do not let an editor rewrite the packets.

**`jsonschema` or `pyyaml` missing.** `python -m pip install -r
requirements-review.txt`.
