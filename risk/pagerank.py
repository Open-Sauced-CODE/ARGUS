"""
ARGUS Phase 2 — Personalised PageRank (PPR) scorer.

Graph convention: a networkx.DiGraph where every edge has attribute ``p``
(0 < p <= 1) and ``etype`` (str); nodes have ``kind`` and ``label``.

Module constant ``ABSORB`` is the synthetic sink node added by
``_with_absorb``; it should never appear in caller code.
"""

import json
import pathlib

import numpy as np
import networkx as nx  # imported for type hints / doc; NOT called for pagerank

ABSORB: str = "__ABSORB__"

_CONFIG_PATH = pathlib.Path(__file__).parent / "damping_config.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _with_absorb(G: nx.DiGraph) -> nx.DiGraph:
    """Return a new DiGraph that is G extended with a synthetic ABSORB sink.

    For each node *u* the outgoing edge weights ``w`` are derived from the
    existing ``p`` attributes as follows:

    * Compute ``s = sum(p for each outgoing edge of u)``.
    * If ``s > 1``:  ``w = p / s``  (re-scale so the row sums to 1;
      no ABSORB edge is needed).
    * If ``s <= 1``: ``w = p``  (magnitude is preserved — a lone p=0.1 edge
      stays at w=0.1, not normalised to 1.0).
    * If ``s < 1``:  add ``u -> ABSORB``  with  ``w = 1 - s``.

    ABSORB itself has no outgoing edges (it is a dangling/sink node in the
    transition matrix built by ``ppr_power_iteration``).

    Parameters
    ----------
    G : nx.DiGraph
        Input graph.  **G is never modified.**

    Returns
    -------
    nx.DiGraph
        New graph with all nodes of G plus ABSORB; edges carry attribute ``w``.
    """
    H = nx.DiGraph()
    H.add_nodes_from(G.nodes(data=True))
    H.add_node(ABSORB)

    for u in G.nodes():
        out_edges = list(G.out_edges(u, data=True))
        s = sum(data.get("p", 0.0) for _, _, data in out_edges)

        if s > 1.0:
            # Row over-specified: scale down so weights sum to 1.
            for _, v, data in out_edges:
                H.add_edge(u, v, w=data["p"] / s, etype=data.get("etype", ""))
        else:
            # Row under- or exactly-specified: keep magnitudes.
            for _, v, data in out_edges:
                H.add_edge(u, v, w=data["p"], etype=data.get("etype", ""))
            if s < 1.0:
                H.add_edge(u, ABSORB, w=1.0 - s)

    return H


def ppr_power_iteration(
    H: nx.DiGraph,
    personalization: dict,
    alpha: float = 0.85,
    tol: float = 1e-12,
    max_iter: int = 1000,
) -> dict:
    """Personalised PageRank via power iteration.

    Uses **numpy only** (networkx.pagerank is NOT called here).

    Parameters
    ----------
    H : nx.DiGraph
        Graph whose edges carry attribute ``w``.
    personalization : dict
        ``{node: non-negative weight}``.  Normalised internally to sum 1 to
        form the restart vector *e*.
    alpha : float
        Probability of following an edge (teleportation probability =
        ``1 - alpha``).  Same semantics as networkx's ``alpha``.
    tol : float
        Convergence threshold: stop when ``sum(|pi_new - pi|) < tol``.
    max_iter : int
        Hard iteration cap.

    Returns
    -------
    dict
        ``{node: float}`` — sums to 1 over *all* nodes in H.

    Notes
    -----
    Iteration formula::

        pi_new = alpha * (P.T @ pi  +  sum_dangling(pi) * e)  +  (1 - alpha) * e

    where *P* is the row-normalised transition matrix built from edge weight
    ``w``, and *dangling* nodes are those whose row in *P* is all-zero.
    """
    nodes = list(H.nodes())
    n = len(nodes)
    idx = {node: i for i, node in enumerate(nodes)}

    # ---- Build restart vector e ----------------------------------------- #
    total = sum(v for v in personalization.values() if v > 0)
    e = np.zeros(n, dtype=float)
    for node, weight in personalization.items():
        if node in idx and weight > 0:
            e[idx[node]] = weight / total

    # ---- Build transition matrix P[from_row, to_col] -------------------- #
    P = np.zeros((n, n), dtype=float)
    for u, v, data in H.edges(data=True):
        P[idx[u], idx[v]] = data.get("w", 0.0)

    # Normalise each non-empty row to sum 1 (no-op when H comes from
    # _with_absorb, since those rows already sum to 1 by construction).
    row_sums = P.sum(axis=1)
    for i in range(n):
        if row_sums[i] > 0.0:
            P[i] /= row_sums[i]

    # Recompute after normalisation to identify dangling nodes (row sum == 0).
    row_sums = P.sum(axis=1)
    dangling_mask = row_sums == 0.0

    PT = P.T
    pi = e.copy()

    for _ in range(max_iter):
        dangling_sum = float(pi[dangling_mask].sum())
        pi_new = alpha * (PT @ pi + dangling_sum * e) + (1.0 - alpha) * e
        if np.sum(np.abs(pi_new - pi)) < tol:
            pi = pi_new
            break
        pi = pi_new

    return {node: float(pi[idx[node]]) for node in nodes}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_digraph(
    G: nx.DiGraph,
    entry_nodes=None,
    damping: float | None = None,
) -> dict:
    """Score every node in G with Personalised PageRank.

    This is a **pure function**: G is never modified.

    Parameters
    ----------
    G : nx.DiGraph
        Attack graph.  Every edge must carry ``p`` (0 < p <= 1) and
        ``etype`` (str).
    entry_nodes : list[node] or None
        PPR restart set.  If *None*, resolved via
        ``risk.attack_graph.resolve_entry_nodes`` (lazy import).
        Only nodes actually present in G are kept; if none remain a
        :class:`ValueError` is raised.
    damping : float or None
        Alpha / damping factor (0 < damping < 1).  If *None*, read from
        ``risk/damping_config.json`` adjacent to this file.

    Returns
    -------
    dict
        ``{node: float}`` — ABSORB is excluded; values sum to < 1 (the
        remainder is absorbed by the ABSORB sink).

    Raises
    ------
    ValueError
        * Graph is empty.
        * Any edge is missing ``p``, or ``p <= 0``, or ``p > 1``.
        * No entry nodes found (after intersection with G's nodes).
        * ``damping`` is not strictly between 0 and 1.
    """
    # ---------------------------------------------------------------------- #
    # 1. Basic validation
    # ---------------------------------------------------------------------- #
    if len(G) == 0:
        raise ValueError("Graph is empty")

    for u, v, data in G.edges(data=True):
        p = data.get("p")
        if p is None:
            raise ValueError(
                "Edge ({!r}, {!r}) is missing the required attribute 'p'".format(u, v)
            )
        if p <= 0 or p > 1:
            raise ValueError(
                "Edge ({!r}, {!r}) has invalid p={!r}: must satisfy 0 < p <= 1".format(
                    u, v, p
                )
            )

    # ---------------------------------------------------------------------- #
    # 2. Resolve entry nodes
    # ---------------------------------------------------------------------- #
    if entry_nodes is None:
        # Lazy import — risk.attack_graph may not exist yet; a top-level
        # import would break importing this module.
        from risk.attack_graph import resolve_entry_nodes  # noqa: PLC0415
        entry_nodes = resolve_entry_nodes(G)

    entry_nodes = [n for n in entry_nodes if n in G]
    if not entry_nodes:
        raise ValueError("No entry nodes found in graph")

    # ---------------------------------------------------------------------- #
    # 3. Resolve damping
    # ---------------------------------------------------------------------- #
    if damping is None:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            damping = json.load(fh)["damping"]

    if not (0 < damping < 1):
        raise ValueError(
            "damping must satisfy 0 < damping < 1, got {!r}".format(damping)
        )

    # ---------------------------------------------------------------------- #
    # 4. Build absorbing graph and run PPR
    # ---------------------------------------------------------------------- #
    H = _with_absorb(G)
    personalization = {n: 1.0 for n in entry_nodes}
    pi = ppr_power_iteration(H, personalization, alpha=damping)

    # Remove the synthetic ABSORB sink before returning.
    pi.pop(ABSORB, None)
    return pi


def score_graph(session) -> dict:
    """Score the live attack graph fetched from a Neo4j *session*.

    Lazy-imports ``build_attack_graph`` from ``risk.attack_graph`` to avoid
    making that module a hard dependency when importing this one.
    """
    from risk.attack_graph import build_attack_graph  # noqa: PLC0415
    return score_digraph(build_attack_graph(session))


def to_percent(pi: dict, exclude: tuple = ()) -> dict:
    """Rescale PPR scores to a 0-100 percentage scale.

    The reference maximum is the highest score among nodes that are:
      * **not** in ``exclude``, and
      * **not** equal to ``"INTERNET"``.

    If that maximum is 0, every node is mapped to 0.

    Parameters
    ----------
    pi : dict
        ``{node: float}`` as returned by ``score_digraph``.
    exclude : tuple
        Additional node IDs to skip when searching for the maximum.

    Returns
    -------
    dict
        ``{node: float}`` with values in [0, 100].
    """
    skip = set(exclude) | {"INTERNET"}
    candidates = {node: score for node, score in pi.items() if node not in skip}
    if not candidates:
        return {node: 0.0 for node in pi}
    max_score = max(candidates.values())
    if max_score == 0.0:
        return {node: 0.0 for node in pi}
    return {node: (score / max_score) * 100.0 for node, score in pi.items()}
