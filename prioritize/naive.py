"""
ARGUS Phase 3 — Naive greedy baseline.

Scores findings by the PPR (Personalised PageRank) score of their target node,
sorts descending, and greedily takes findings that fit the remaining budget
(skips unaffordable ones and continues).

COMPARISON BASELINE ONLY — not for production prioritization.
Use prioritize.interdiction.prioritize() for production.

Public API:
    naive_select(G, entry, findings, budget, ppr=None) -> dict
"""

from risk.pagerank import score_digraph


def naive_select(G, entry, findings, budget, ppr=None):
    """Greedy-PPR baseline selection.

    Parameters
    ----------
    G : nx.DiGraph
        Phase 2 attack graph (never mutated).
    entry : list
        Entry node ids (used to compute PPR if ppr is None).
    findings : list[dict]
        Findings from enumerate_findings().
    budget : numeric
        Total budget.
    ppr : dict or None
        Pre-computed PPR scores {node: float}.  If None, recomputed.

    Returns
    -------
    dict with keys:
        selected : list[str]  finding ids chosen (in greedy order)
        ordered  : list[dict] all findings sorted by PPR score desc
    """
    entry = [e for e in entry if e in G]

    if ppr is None:
        try:
            ppr = score_digraph(G, entry)
        except Exception:
            ppr = {}

    # Score each finding by PPR of its target node
    def _sort_key(f):
        score = ppr.get(f["target"], 0.0)
        # Descending score, ascending cost for ties, then finding_id
        return (-score, f["cost"], f["finding_id"])

    ordered = sorted(findings, key=_sort_key)

    selected = []
    remaining = budget
    for f in ordered:
        if f["cost"] <= remaining + 1e-9:
            selected.append(f["finding_id"])
            remaining -= f["cost"]

    return {"selected": selected, "ordered": ordered}
