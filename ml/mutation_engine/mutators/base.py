"""Base class every mutator follows (Phase 5, Step 5)."""

from ml.mutation_engine.model import MISSING, Mutation


class Mutator:
    mutator_id = ""
    resource_types = ()
    variants = {}            # variant name -> sampling weight
    rules = ()               # rule ids a variant makes fire (deny or warn)
    writes = frozenset()     # attributes this mutator canonicalises or changes
    route = "fix"            # "fix" or "escalate"
    reason = ""              # escalate reason

    def rules_for(self, variant):
        return list(self.rules)

    def prepare(self, res, variant):
        """Return a CLEAN copy of `res` with any value the model could not see after the mutation set to its
        canonical value, or None when this variant cannot be applied to `res`."""
        raise NotImplementedError

    def mutate(self, clean, variant):
        """Return (broken copy, Mutation). `clean` is what prepare() returned."""
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------------------------
    def _mutation(self, variant, before_res, after_res, paths, inverse_ops):
        before = {p: before_res.attrs.get(p, MISSING) for p in paths}
        after = {p: after_res.attrs.get(p, MISSING) for p in paths}
        return Mutation(self.mutator_id, variant, self.rules_for(variant), list(paths), before, after,
                        inverse_ops, self.route)

    def _escalate_ops(self):
        return [{"op": "escalate", "reason": self.reason}]
