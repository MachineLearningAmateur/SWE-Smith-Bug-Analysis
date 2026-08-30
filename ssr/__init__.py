"""SSR-style bug generation, validation, sampling and blind review over
SWE-smith environments.

Layering:

    ssr.paths          repository locations
    ssr.util           hashing, deterministic JSON, seeded RNG, logging
    ssr.config         YAML config loading with schema-free validation
    ssr.exec_env       sandboxed command execution (docker / wsl / local)
    ssr.model          OpenRouter chat client and offline replacements
    ssr.action_protocol   the strict textual action protocol
    ssr.agent_loop     injector and solver agent loops
    ssr.artifacts      the SSR per-bug artifact bundle
    ssr.validation     the eight execution-validation checks
    ssr.dedup          deterministic duplicate detection
    ssr.sampling       deterministic stratified selection of the final 100
    ssr.packets        neutral review packets and the leakage scan
    ssr.taxonomy       frozen taxonomy loading and family derivation
    ssr.metrics        objective, non-LLM patch metrics
    ssr.review_workflow  reviewer directories, progress and completion

Nothing in this package may read a taxonomy label while generating,
deduplicating or sampling bugs. ``ssr.sampling`` enforces that at runtime.
"""

__version__ = "0.1.0"
PROTOCOL_VERSION = "ssr-action-protocol/1"
VALIDATOR_VERSION = "ssr-validator/1"
