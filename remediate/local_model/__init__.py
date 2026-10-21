"""
ARGUS Phase 5, Step 22 - T1: the local fine-tuned model M1 served by Ollama (schema-constrained decoding).

    generate(tokenized_finding, n=8, model=None)            -> list[Patch-IR dict]   (only schema-valid candidates, first = greedy)
    generate_with_stats(tokenized_finding, n=8, model=None) -> (candidates, stats)   (for Phase 6: agreement rate, log-probability statistics)

`tokenized_finding` is the airlock output. The model name comes from the argument or the ARGUS_M1_MODEL environment variable
(default argus-m1-rft). Nothing here ever leaves the machine (Ollama runs locally). Frozen signatures: do not change without telling the team.
"""

import json
import os

from ml.mutation_engine.labeler import schema_errors
from ml.train_m1.eval.ollama_client import chat_once

DEFAULT_MODEL = "argus-m1-rft"
TEMPERATURE = 0.7


def _model(model):
    return model or os.environ.get("ARGUS_M1_MODEL", DEFAULT_MODEL)


def _raw(finding, n, model, logprobs):
    return [chat_once(_model(model), finding, 0.0 if i == 0 else TEMPERATURE, seed=i, logprobs=logprobs) for i in range(n)]


def _parse(content):
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return None
    return None if schema_errors(data) else data


def generate(tokenized_finding, n=8, model=None):
    out = []
    for reply in _raw(tokenized_finding, n, model, False):
        patch = _parse(reply["content"])
        if patch is not None:
            out.append(patch)
    return out


def generate_with_stats(tokenized_finding, n=8, model=None):
    replies = _raw(tokenized_finding, n, model, True)
    candidates, canon_counts, lp_means, lp_mins = [], {}, [], []
    for reply in replies:
        patch = _parse(reply["content"])
        if patch is None:
            continue
        candidates.append(patch)
        key = json.dumps(patch["ops"], sort_keys=True)
        canon_counts[key] = canon_counts.get(key, 0) + 1
        lps = [t.get("logprob") for t in (reply.get("logprobs") or []) if isinstance(t, dict) and t.get("logprob") is not None]
        if lps:
            lp_means.append(sum(lps) / len(lps))
            lp_mins.append(min(lps))
    stats = {"n_requested": n, "n_valid": len(candidates),
             "agreement_rate": (max(canon_counts.values()) / len(candidates)) if candidates else 0.0,
             "logprob_mean": (sum(lp_means) / len(lp_means)) if lp_means else None,
             "logprob_min": min(lp_mins) if lp_mins else None}
    return candidates, stats
