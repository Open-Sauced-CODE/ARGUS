"""Registry of the 12 mutators named in ml/README_contracts.md (Phase 5, Step 5)."""

from ml.mutation_engine.mutators.escalate import AccountDetectionOff, AccountMfaOff, RdsUnencrypted, RegionOutsideApproved
from ml.mutation_engine.mutators.iam import IamFullAdmin
from ml.mutation_engine.mutators.network import SgWorldOpen
from ml.mutation_engine.mutators.s3 import LifecycleOff, LoggingOff, PublicBlockOff, SseAlgo, SseOff, VersioningOff

ALL_MUTATORS = [
    SseOff(), SseAlgo(), RdsUnencrypted(), VersioningOff(), LifecycleOff(), PublicBlockOff(), SgWorldOpen(),
    IamFullAdmin(), AccountMfaOff(), LoggingOff(), AccountDetectionOff(), RegionOutsideApproved(),
]
BY_ID = {m.mutator_id: m for m in ALL_MUTATORS}


def rules_covered():
    """{rule id: [mutator ids]} for every rule any mutator makes fire."""
    out = {}
    for m in ALL_MUTATORS:
        for rule in m.rules:
            out.setdefault(rule, []).append(m.mutator_id)
    return out


def variant_count():
    return sum(len(m.variants) for m in ALL_MUTATORS)
