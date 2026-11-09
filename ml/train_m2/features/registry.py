"""Feature registry for M2 (Shaurya-owned). One source of truth for names, groups, monotonicity and the spec hash.

Implemented groups: U uncertainty (token logprobs), C consensus (the N drafts of one input), S structure, R rule/generator.
NOT implemented in this version (documented, not hidden): X cross-tier, G graph context, H gate evidence. Adding or
changing any feature bumps FEATURE_SET_VERSION and therefore spec_hash(); the model refuses a mismatched vector.
Logprob semantics: tokens[].lp are RAW logprobs reported before the presence penalty and grammar mask (the greedy
token is not the top-1 token for 7-8% of zeroshot/rft_v2 tokens), so U features measure raw model confidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

FEATURE_SET_VERSION = "1"
KNOWN_RULES = ("cis.iam_no_full_admin", "cis.s3_default_encryption", "cis.s3_public_access_block", "cis.sg_open_ingress",
               "dpdp.rule15_region", "dpdp.rule6_account_mfa", "dpdp.rule6_logging", "dpdp.rule6_public_exposure",
               "dpdp.rule6_sg_open_ingress", "dpdp.rule6_versioning", "dpdp.rule6a", "dpdp.rule6a_rds",
               "dpdp.rule7_detection", "dpdp.rule8_lifecycle")
GENERATORS = ("zeroshot", "sft", "rft", "rft_v2", "sft_oof")
OP_TYPES = ("set_attr", "enable_feature", "restrict_cidr", "set_lifecycle_rule", "add_policy_statement",
            "remove_policy_statement", "escalate")


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: str
    monotone: int = 0          # +1 higher is safer, -1 lower is safer, 0 free
    description: str = ""
    dtype: str = "float"


def _u(n, m, d): return FeatureSpec(n, "U", m, d)
def _c(n, m, d): return FeatureSpec(n, "C", m, d)
def _s(n, m, d): return FeatureSpec(n, "S", m, d)
def _r(n, m, d): return FeatureSpec(n, "R", m, d)


REGISTRY: tuple[FeatureSpec, ...] = (
    _u("lp_mean", 1, "mean token logprob"), _u("lp_min", 1, "minimum token logprob"),
    _u("lp_p10", 1, "10th percentile token logprob"), _u("lp_std", -1, "std of token logprobs"),
    _u("seq_logprob", 1, "sum of token logprobs"), _u("lp_on_op_token", 1, "mean logprob of the tokens spelling op names"),
    _u("lp_min_on_value_tokens", 1, "min logprob over the tokens spelling op values"),
    _u("entropy_mean", -1, "mean entropy of the renormalised top-k"), _u("top1_top2_margin_mean", 1, "mean top1-top2 logprob gap"),
    _c("agreement_rate", 1, "share of the cohort with the same canonical answer"), _c("n_distinct_patches", -1, "distinct canonical answers"),
    _c("modal_share", 1, "share of the modal answer"), _c("greedy_is_modal", 1, "greedy sample equals the modal answer"),
    _c("cluster_entropy_norm", -1, "entropy of answer shares / ln N"), _c("n_valid_over_n_requested", 1, "parseable drafts / N"),
    _s("n_ops", -1, "number of ops"), *[_s(f"n_{o}", 0, f"count of {o} ops") for o in OP_TYPES],
    _s("writes_only_rule_fields_frac", 1, "share of attribute ops that write fields the rule reads"),
    _s("patch_chars", 0, "characters of the raw answer"), _s("uses_placeholder", 0, "answer contains INTERNAL_CIDR"),
    _r("rule_is_dpdp", 0, "rule library"), _r("rule_code", 0, "index of the rule in KNOWN_RULES (-1 unknown)"),
    _r("n_rule_fields", 0, "fields the rule reads"), _r("route_is_escalate", 0, "meta.route == escalate"),
    *[_r(f"gen_{g}", 0, f"generator is {g}") for g in GENERATORS],
)


def spec_hash(specs: tuple[FeatureSpec, ...] | None = None) -> str:
    payload = json.dumps({"version": FEATURE_SET_VERSION, "specs": [asdict(s) for s in (specs or REGISTRY)]},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def names(groups: tuple[str, ...] | None = None) -> list[str]:
    return [s.name for s in REGISTRY if groups is None or s.group in groups]


def monotone_vector(feature_names: list[str]) -> list[int]:
    by = {s.name: s.monotone for s in REGISTRY}
    return [by[n] for n in feature_names]


def feature_spec_md() -> str:
    L = [f"# M2 feature spec (version {FEATURE_SET_VERSION}, hash {spec_hash()[:12]})", "",
         "| name | group | monotone | description |", "|---|---|---|---|"]
    L += [f"| {s.name} | {s.group} | {s.monotone:+d} | {s.description} |" for s in REGISTRY]
    return "\n".join(L) + "\n"
