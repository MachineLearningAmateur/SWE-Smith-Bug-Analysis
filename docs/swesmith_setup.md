# SWE-smith environment setup

SWE-smith is the environment layer only (see `docs/research_scope.md`). This
document covers getting one running and recording what was used.

## Current status on this machine

`python scripts/check_environment.py` reports what is present. As of the
initial build, one required capability is missing and one is blocked:

| Capability | Status | Detail |
|---|---|---|
| Python 3.10+ (harness) | present | 3.13.1 on the Windows host |
| git | present | 2.55.0 |
| Frozen taxonomy | present | hashes verified, mapping matches the handoff |
| `OPENROUTER_API_KEY` | present | key valid |
| **Docker** | **missing** | not installed on the Windows host or in WSL |
| WSL | present | Ubuntu 20.04.6, Python 3.8.10 |
| `qwen/qwen-2.5-coder-32b-instruct` | **blocked** | see below |

Two things must be resolved before a corpus run.

### 1. Docker

SWE-smith distributes its environments as Docker images. Without Docker there
is no SWE-smith environment, and the `docker` backend cannot start.

Installing Docker needs administrator rights, which this session does not
have: `sudo` in the WSL distribution asks for a password. Someone with
administrator access must do one of:

* **Docker Desktop for Windows** with WSL2 integration. After installing,
  enable integration for the Ubuntu distribution in Settings → Resources → WSL
  integration. This is the least work.
* **Docker Engine inside WSL**, following Docker's own instructions for
  Ubuntu, then starting the daemon (`sudo service docker start`, or enable
  `systemd` in `/etc/wsl.conf`).

Verify with `docker info`, then re-run `python scripts/check_environment.py`.

### 2. The WSL distribution is Ubuntu 20.04 with Python 3.8

SWE-smith needs Python 3.10 or later. Ubuntu 20.04 ships 3.8. Either:

* install Ubuntu 22.04 alongside it (`wsl --install -d Ubuntu-22.04`) and set
  `SSR_WSL_DISTRO` to the new distribution, or
* install a newer Python into the existing distribution (deadsnakes, or a
  user-space conda/micromamba, which needs no root).

This only matters for running SWE-smith's own tooling. The bug harness itself
runs on the Windows host and talks to containers through `docker exec`, so
the container's Python is what the injector actually uses.

### 3. The configured model is blocked for this account

`qwen/qwen-2.5-coder-32b-instruct` is listed on OpenRouter but is currently
served by one provider only, `cloudflare`, and this account's privacy setting
does not permit that provider. A live call returns:

```
No allowed providers are available for the selected model.
Providers serving qwen/qwen-2.5-coder-32b-instruct: cloudflare,
but your account's allowed-providers setting permits only: ...
```

Two ways forward, and the choice is a research decision, not a technical one:

* **Permit the provider** at <https://openrouter.ai/settings/privacy>. This
  keeps the handoff's model exactly. Preferred.
* **Substitute a model**, changing `model.name` in both
  `configs/generator.yaml` and `configs/solver.yaml`. Reachable alternatives
  on this account, closest in scale first: `qwen/qwen3-coder-30b-a3b-instruct`
  (30B, but a mixture-of-experts model with ~3B active parameters, so not
  scale-comparable in the way the handoff intends), `qwen/qwen3-coder-next`,
  `qwen/qwen3-coder`. Any substitution must be recorded in
  `docs/fidelity_limitations.md` before generation starts.

Note also that `qwen/qwen-2.5-coder-32b-instruct` has a 32,768-token context.
`agent_loop.context_window_turns` in `configs/generator.yaml` exists to keep
long trajectories inside that window; do not raise it without checking.

Confirm the model with `python scripts/check_environment.py --probe-model`,
which makes one small paid call.

## Installing SWE-smith

Follow the current upstream instructions at
<https://github.com/SWE-bench/SWE-smith>. Install it **inside the Linux
environment**, not on the Windows host. Then record what you used:

```bash
git -C /path/to/SWE-smith rev-parse HEAD      # swesmith_sha
python -c "import swesmith; print(swesmith.__version__)"
docker --version
uname -a
```

Every one of those fields has a slot in
`schemas/generation_metadata.schema.json` and is written into each bug's
`metadata.json` automatically by `ssr/exec_env.py`. Nothing needs to be
transcribed by hand.

## Declaring environments

Add entries to `configs/environments.yaml`:

```yaml
environments:
  pvlib_python:
    backend: docker
    image: jyangballin/swesmith.x86_64.pvlib_1776_pvlib-python.<tag>
    repo_path: /testbed
    upstream: pvlib/pvlib-python
    language: python
```

`upstream` is the neutral project name that appears in review packets. Do not
put the SWE-smith image name there: the packet leakage scan in
`ssr/packets.py` rejects it, which is the intended behaviour.

Nothing else may go in these entries. A `test_cmd`, a `log_parser`, a
`problem_statement` or a `FAIL_TO_PASS` key would be picked up by
`ssr.agent_loop.make_forbidden_context` and cause the injector to refuse to
run, because the injector must discover the tests itself.

## Choosing which environments to use

`data/sampling/aidev_environment_profile.json` records the neutral language
mix of the strict AIDev corpus. As built, it reads:

| Language | Share of the strict AIDev corpus |
|---|---:|
| typescript | 34.3% |
| go | 14.3% |
| python | 11.4% |
| unknown | 11.4% |
| rust | 8.6% |
| csharp | 5.7% |
| java | 5.7% |
| cpp, php, c | 2.9% each |

SWE-smith's environment set is overwhelmingly Python. A close language match
is therefore **not achievable**, and pretending otherwise would be worse than
recording the gap. Take whatever non-Python environments SWE-smith offers,
let `scripts/select_review_sample.py` record the deviation, and state the
mismatch in the paper. `docs/fidelity_limitations.md` carries it.

## Keeping heavy artifacts out of Git

Docker layers, source worktrees, package caches and toolchains must stay
outside the repository. `.gitignore` excludes `workspace/`, and
`SSR_WORKSPACE_ROOT` moves that root anywhere you like. A Linux scratch
location such as `~/algoverse/ssr_swesmith_workspace/` is a good choice: WSL
filesystem access from Windows paths is slow.

## The three execution backends

| Backend | Isolated | Valid for a corpus run | Purpose |
|---|---|---|---|
| `docker` | yes | **yes** | SWE-smith images. The intended backend. |
| `wsl` | partly | no | A Linux worktree when Docker is absent. Diagnostics. |
| `local` | no | no | Proving the harness on the host. |

The backend is recorded in every bug's metadata, and
`ssr.pool.eligible_entries` drops `local` candidates from the sampling frame,
so a harness-proving bug cannot reach the review set by accident.
