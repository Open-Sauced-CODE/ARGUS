"""Which route a rule has (fix or escalate), derived from the mutator registry so it can never drift from the contracts table."""

from ml.mutation_engine.mutators import BY_ID, rules_covered


def rule_route(rule_id):
    mutators = rules_covered().get(rule_id, [])
    if mutators and all(BY_ID[m].route == "escalate" for m in mutators):
        return "escalate"
    return "fix"
