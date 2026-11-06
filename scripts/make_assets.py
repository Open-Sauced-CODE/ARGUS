"""
ARGUS Visual Asset Generator
Generates high-resolution, dark-themed visual assets for the repository:
1. docs/assets/social_preview.png (1280x640 px)
2. docs/assets/architecture.png (1600x700 px)
3. docs/assets/pipeline_status.png (1500x380 px)

Palette:
- Background: #0d1117
- Card / Panel: #161b22
- Borders: #30363d
- Teal Accent: #2dd4bf
- Amber Accent: #f59e0b
- Text Primary: #f0f6fc
- Text Muted: #8b949e
"""

import os
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import networkx as nx

ASSETS_DIR = Path("docs/assets")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

FONT_FAMILY = "sans-serif"
BG_COLOR = "#0d1117"
CARD_BG = "#161b22"
BORDER_COLOR = "#30363d"
TEAL = "#2dd4bf"
AMBER = "#f59e0b"
TEXT_WHITE = "#f0f6fc"
TEXT_MUTED = "#8b949e"
GREEN = "#3fb950"
PURPLE = "#a371f7"


def generate_social_preview():
    """Generates docs/assets/social_preview.png (exactly 1280x640 px)."""
    fig_w, fig_h = 12.8, 6.4
    dpi = 100
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor=BG_COLOR)
    ax = fig.add_axes([0, 0, 1, 1], facecolor=BG_COLOR)
    ax.set_xlim(0, 1280)
    ax.set_ylim(0, 640)
    ax.axis("off")

    # Background subtle grid lines
    for x in range(0, 1281, 80):
        ax.plot([x, x], [0, 640], color="#161b22", lw=0.6, alpha=0.5, zorder=1)
    for y in range(0, 641, 80):
        ax.plot([0, 1280], [y, y], color="#161b22", lw=0.6, alpha=0.5, zorder=1)

    # Stylized Decorative Attack Graph on the right (x: 740..1200, y: 100..560)
    np.random.seed(1337)
    G = nx.erdos_renyi_graph(16, 0.22, seed=1337)
    # Ensure connectivity
    pos = nx.spring_layout(G, seed=1337, center=(980, 320), scale=210)

    # Draw edges
    for u, v in G.edges():
        p1, p2 = pos[u], pos[v]
        ax.plot(
            [p1[0], p2[0]],
            [p1[1], p2[1]],
            color="#2dd4bf",
            alpha=0.25,
            lw=1.5,
            zorder=2,
        )

    # Highlight an attack path
    attack_path = [2, 7, 11, 4]
    for i in range(len(attack_path) - 1):
        u, v = attack_path[i], attack_path[i + 1]
        p1, p2 = pos[u], pos[v]
        ax.plot(
            [p1[0], p2[0]],
            [p1[1], p2[1]],
            color=AMBER,
            alpha=0.85,
            lw=3.0,
            linestyle="--",
            zorder=3,
        )

    # Draw graph nodes
    for node, (nx_x, nx_y) in pos.items():
        if node in attack_path:
            node_col = AMBER
            size = 140
        else:
            node_col = TEAL
            size = 90
        # Glow circle
        ax.scatter([nx_x], [nx_y], s=size * 3.5, color=node_col, alpha=0.15, zorder=3)
        ax.scatter([nx_x], [nx_y], s=size, color=node_col, alpha=0.85, zorder=4, edgecolors=BG_COLOR, linewidths=1.5)

    # Graph badge
    g_card = patches.FancyBboxPatch(
        (850, 40), 280, 38,
        boxstyle="round,pad=0.2,rounding_size=6",
        facecolor=CARD_BG, edgecolor=BORDER_COLOR, lw=1, zorder=4
    )
    ax.add_patch(g_card)
    ax.text(990, 58, "Illustrative AWS Attack Graph", color=TEXT_MUTED, fontsize=9.5,
            ha="center", va="center", family=FONT_FAMILY, zorder=5)

    # Left content: Brand, Titles, Features
    # Top badge
    badge = patches.FancyBboxPatch(
        (80, 530), 295, 34,
        boxstyle="round,pad=0.2,rounding_size=6",
        facecolor="#1f242c", edgecolor=TEAL, lw=1.2, zorder=4
    )
    ax.add_patch(badge)
    ax.text(227, 547, "OPEN-SAUCED CODE  |  CLOUD SECURITY", color=TEAL, fontsize=9.5,
            fontweight="bold", ha="center", va="center", family=FONT_FAMILY, zorder=5)

    # Title
    ax.text(80, 440, "ARGUS", color=TEXT_WHITE, fontsize=54, fontweight="bold",
            ha="left", va="center", family=FONT_FAMILY, zorder=5)

    # Subtitle
    sub_text = (
        "Game-theoretic, graph-driven risk prioritization\n"
        "and India DPDP Act compliance verification for AWS"
    )
    ax.text(80, 350, sub_text, color="#c9d1d9", fontsize=17, fontweight="medium",
            ha="left", va="center", family=FONT_FAMILY, linespacing=1.4, zorder=5)

    # Key feature pills
    features = [
        ("Personalized PageRank", TEAL),
        ("Budgeted Interdiction", AMBER),
        ("Zero-Data Privacy Airlock", GREEN),
        ("DPDP Rules 6, 7, 8, 15", PURPLE),
    ]
    cur_x = 80
    for text, color in features:
        pill_w = len(text) * 8.6 + 24
        pill = patches.FancyBboxPatch(
            (cur_x, 240), pill_w, 32,
            boxstyle="round,pad=0.2,rounding_size=6",
            facecolor=CARD_BG, edgecolor=color, lw=1, zorder=4
        )
        ax.add_patch(pill)
        ax.text(cur_x + pill_w / 2, 256, text, color=TEXT_WHITE, fontsize=10.5,
                ha="center", va="center", family=FONT_FAMILY, zorder=5)
        cur_x += pill_w + 14

    # Bottom separation line
    ax.plot([80, 1200], [140, 140], color=BORDER_COLOR, lw=1, zorder=3)

    # Footer line
    footer_text = "Privacy-first Architecture   *   Local Remediation Models   *   Deterministic Verification Gates"
    ax.text(80, 95, footer_text, color=TEXT_MUTED, fontsize=12,
            ha="left", va="center", family=FONT_FAMILY, zorder=5)

    out_path = ASSETS_DIR / "social_preview.png"
    plt.savefig(out_path, dpi=dpi, facecolor=BG_COLOR)
    plt.close()
    print(f"Generated {out_path} (1280x640)")


def generate_architecture():
    """Generates docs/assets/architecture.png (1600x700 px)."""
    fig_w, fig_h = 16.0, 7.0
    dpi = 100
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor=BG_COLOR)
    ax = fig.add_axes([0, 0, 1, 1], facecolor=BG_COLOR)
    ax.set_xlim(0, 1600)
    ax.set_ylim(0, 700)
    ax.axis("off")

    # Header
    ax.text(80, 645, "ARGUS SYSTEM ARCHITECTURE", color=TEXT_WHITE, fontsize=20,
            fontweight="bold", ha="left", va="center", family=FONT_FAMILY)
    ax.text(80, 615, "End-to-End Privacy-Preserving Cloud Attack Graph, Remediation, and DPDP Verification Pipeline",
            color=TEXT_MUTED, fontsize=11.5, ha="left", va="center", family=FONT_FAMILY)

    # Boxes definition: [x, y, w, h, title, subtitle, color, is_planned]
    # Stages horizontally across 1600 width:
    # 1. AWS Ingest (80)
    # 2. Risk Engine (330)
    # 3. Interdiction (580)
    # 4. Privacy Airlock (830)
    # 5. Remediation Tiers (1080)
    # 6. Gate & Auto-Apply (1340)

    stages = [
        # Ingestion
        {"x": 60, "y": 300, "w": 200, "h": 220, "title": "1. Graph Ingestion",
         "sub": "AWS Read-Only APIs\nCartography Sync\nNeo4j Attack Graph\n(Nodes, IAM, Policies)",
         "color": TEAL, "planned": False},
        # Risk Engine
        {"x": 290, "y": 300, "w": 200, "h": 220, "title": "2. Risk Engine",
         "sub": "Personalized PageRank\nSimulated Random Walk\nChained Lateral Paths\nCrown Jewel Scoring",
         "color": TEAL, "planned": False},
        # Interdiction
        {"x": 520, "y": 300, "w": 200, "h": 220, "title": "3. Decision Engine",
         "sub": "Network Interdiction\nBudgeted Cut-Set Opt\nMax Attacker Cost\nTop-k Finding Selection",
         "color": TEAL, "planned": False},
        # Privacy Airlock
        {"x": 750, "y": 300, "w": 210, "h": 220, "title": "4. Privacy Airlock",
         "sub": "Structural Projection\nHMAC-SHA256 Tokenizer\nRegex Sensitive Scrub\nZero Creds / PII to LLM",
         "color": GREEN, "planned": False},
        # Remediation Tiers
        {"x": 990, "y": 250, "w": 270, "h": 290, "title": "5. Remediation Tiers",
         "sub": "T0: Deterministic Templates\n(Known safe CIS patterns)\n\n"
                "T1: Local Fine-Tuned M1\n(Qwen2.5-Coder Patch-IR)\n\n"
                "T2: Remote LLM (Opt-in)\n(De-identified prompt)\n\n"
                "T3: Human Escalation (Planned)",
         "color": AMBER, "planned": False},
        # Verification Gate & Resolution
        {"x": 1290, "y": 250, "w": 260, "h": 290, "title": "6. Verification & Trust",
         "sub": "OPA / Rego Verification Gate\n* CIS generic safety\n* DPDP Rules 6, 7, 8, 15\n\n"
                "M2 Confidence Model (P6)\n* Conformal error control\n\n"
                "Result Dispatch:\n* Auto-Apply Validated Fix\n* Human Approval Queue",
         "color": PURPLE, "planned": True},
    ]

    for st in stages:
        linestyle = "--" if st["planned"] else "-"
        lw = 1.6 if st["planned"] else 1.8
        card = patches.FancyBboxPatch(
            (st["x"], st["y"]), st["w"], st["h"],
            boxstyle="round,pad=0.2,rounding_size=8",
            facecolor=CARD_BG, edgecolor=st["color"],
            linestyle=linestyle, lw=lw, zorder=3
        )
        ax.add_patch(card)

        # Stage title
        ax.text(st["x"] + st["w"] / 2, st["y"] + st["h"] - 25, st["title"],
                color=st["color"], fontsize=12, fontweight="bold",
                ha="center", va="center", family=FONT_FAMILY, zorder=4)

        if st["planned"]:
            pl_tag = patches.FancyBboxPatch(
                (st["x"] + st["w"] / 2 - 45, st["y"] + st["h"] - 48), 90, 18,
                boxstyle="round,pad=0.2,rounding_size=4",
                facecolor="#261b36", edgecolor=PURPLE, lw=0.8, zorder=4
            )
            ax.add_patch(pl_tag)
            ax.text(st["x"] + st["w"] / 2, st["y"] + st["h"] - 39, "Phase 6 & 7 Planned",
                    color=PURPLE, fontsize=7.5, fontweight="bold", ha="center", va="center",
                    family=FONT_FAMILY, zorder=5)

        # Stage subtext
        sub_y = st["y"] + (st["h"] / 2) - (20 if st["planned"] else 10)
        ax.text(st["x"] + st["w"] / 2, sub_y, st["sub"],
                color=TEXT_WHITE, fontsize=9.2, ha="center", va="center",
                family=FONT_FAMILY, linespacing=1.35, zorder=4)

    # Connecting arrows between stages
    arrows = [
        ((260, 410), (290, 410)),
        ((490, 410), (520, 410)),
        ((720, 410), (750, 410)),
        ((960, 410), (990, 410)),
        ((1260, 410), (1290, 410)),
    ]
    for start, end in arrows:
        ax.annotate(
            "", xy=end, xytext=start,
            arrowprops=dict(
                arrowstyle="-|>",
                color=TEXT_MUTED,
                lw=1.8,
                mutation_scale=14,
            ),
            zorder=3
        )

    # Bottom notes panel
    notes_patch = patches.FancyBboxPatch(
        (60, 40), 1490, 130,
        boxstyle="round,pad=0.2,rounding_size=6",
        facecolor="#12161c", edgecolor=BORDER_COLOR, lw=1, zorder=2
    )
    ax.add_patch(notes_patch)

    ax.text(80, 140, "CORE ARCHITECTURAL PRINCIPLES", color=TEAL, fontsize=11,
            fontweight="bold", ha="left", va="center", family=FONT_FAMILY, zorder=4)

    principles = [
        "1. Never require the AI to be right: The verifier enforces determinism. Model drafts must pass rigorous OPA/Rego gates.",
        "2. Zero Sensitive Cloud Data: The privacy airlock hashes, tokenizes, and strips names/keys before prompts reach any model.",
        "3. Game-Theoretic Priority: Fixes target critical cut-sets (interdiction) rather than individual isolated findings.",
        "4. Verifiable Compliance: Patches map directly to technical safeguards in India's DPDP Rules 2025 (Rules 6, 7, 8, 15)."
    ]
    for idx, p in enumerate(principles):
        py = 112 - (idx * 21)
        ax.text(80, py, p, color=TEXT_WHITE, fontsize=9.2, ha="left", va="center",
                family=FONT_FAMILY, zorder=4)

    out_path = ASSETS_DIR / "architecture.png"
    plt.savefig(out_path, dpi=dpi, facecolor=BG_COLOR)
    plt.close()
    print(f"Generated {out_path} (1600x700)")


def generate_pipeline_status():
    """Generates docs/assets/pipeline_status.png (1500x380 px)."""
    fig_w, fig_h = 15.0, 3.8
    dpi = 100
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor=BG_COLOR)
    ax = fig.add_axes([0, 0, 1, 1], facecolor=BG_COLOR)
    ax.set_xlim(0, 1500)
    ax.set_ylim(0, 380)
    ax.axis("off")

    # Title
    ax.text(50, 340, "ARGUS DEVELOPMENT ROADMAP & PHASE STATUS", color=TEXT_WHITE,
            fontsize=17, fontweight="bold", ha="left", va="center", family=FONT_FAMILY)
    ax.text(50, 310, "Honest project progress tracking across all 13 project phases (Phases 0-12)",
            color=TEXT_MUTED, fontsize=10.5, ha="left", va="center", family=FONT_FAMILY)

    # Phases data
    # status: "done", "in_progress", "planned"
    phases = [
        ("Phase 0", "Setup & Repos", "done"),
        ("Phase 1", "Graph Schema", "done"),
        ("Phase 2", "PageRank Risk", "done"),
        ("Phase 3", "Interdiction Opt", "done"),
        ("Phase 4", "Privacy Airlock", "done"),
        ("Phase 5", "M1 Local Model", "done"),
        ("Phase 6", "M2 Confidence", "in_progress"),
        ("Phase 7", "Gate / Backend", "planned"),
        ("Phase 8", "Dashboard UI", "planned"),
        ("Phase 9", "Testbed Ingest", "planned"),
        ("Phase 10", "Benchmark Eval", "planned"),
        ("Phase 11", "Paper / Report", "planned"),
        ("Phase 12", "Final Release", "planned"),
    ]

    card_w = 98
    card_h = 120
    start_x = 45
    spacing = 112
    card_y = 135

    # Background track connecting cards
    ax.plot([start_x + 30, start_x + 12 * spacing + 50], [card_y + card_h / 2, card_y + card_h / 2],
            color=BORDER_COLOR, lw=3, zorder=1)

    for i, (p_id, p_name, status) in enumerate(phases):
        cx = start_x + (i * spacing)
        if status == "done":
            edge = TEAL
            fill = "#132b2b"
            badge_text = "DONE"
            badge_color = TEAL
            badge_bg = "#1b443c"
            line_style = "-"
        elif status == "in_progress":
            edge = AMBER
            fill = "#2f2212"
            badge_text = "IN PROGRESS"
            badge_color = AMBER
            badge_bg = "#473014"
            line_style = "-"
        else:
            edge = "#30363d"
            fill = CARD_BG
            badge_text = "PLANNED"
            badge_color = TEXT_MUTED
            badge_bg = "#1f242c"
            line_style = "--"

        card = patches.FancyBboxPatch(
            (cx, card_y), card_w, card_h,
            boxstyle="round,pad=0.2,rounding_size=6",
            facecolor=fill, edgecolor=edge,
            linestyle=line_style, lw=1.5, zorder=3
        )
        ax.add_patch(card)

        # Phase ID
        ax.text(cx + card_w / 2, card_y + card_h - 22, p_id,
                color=TEXT_WHITE, fontsize=10.5, fontweight="bold",
                ha="center", va="center", family=FONT_FAMILY, zorder=4)

        # Phase Name
        ax.text(cx + card_w / 2, card_y + card_h / 2 + 2, p_name,
                color=TEXT_WHITE if status != "planned" else TEXT_MUTED,
                fontsize=8.5, ha="center", va="center", family=FONT_FAMILY,
                wrap=True, zorder=4)

        # Status badge
        b_patch = patches.FancyBboxPatch(
            (cx + 8, card_y + 12), card_w - 16, 20,
            boxstyle="round,pad=0.1,rounding_size=4",
            facecolor=badge_bg, edgecolor=badge_color, lw=0.8, zorder=4
        )
        ax.add_patch(b_patch)
        ax.text(cx + card_w / 2, card_y + 22, badge_text,
                color=badge_color, fontsize=7.5, fontweight="bold",
                ha="center", va="center", family=FONT_FAMILY, zorder=5)

    # Legend at the bottom
    ax.plot([50, 1450], [75, 75], color=BORDER_COLOR, lw=0.8, zorder=2)

    legends = [
        ("DONE (Phases 0-5)", TEAL, "#1b443c"),
        ("IN PROGRESS (Phase 6 M2 Risk-Controlled Gate)", AMBER, "#473014"),
        ("PLANNED (Phases 7-12 Backend, UI, Evaluation)", TEXT_MUTED, "#1f242c")
    ]
    cur_lx = 50
    for label, col, bg in legends:
        b_box = patches.FancyBboxPatch(
            (cur_lx, 32), 22, 22,
            boxstyle="round,pad=0.1,rounding_size=4",
            facecolor=bg, edgecolor=col, lw=1, zorder=3
        )
        ax.add_patch(b_box)
        ax.text(cur_lx + 32, 43, label, color=TEXT_WHITE, fontsize=10,
                ha="left", va="center", family=FONT_FAMILY, zorder=4)
        cur_lx += len(label) * 8.5 + 85

    out_path = ASSETS_DIR / "pipeline_status.png"
    plt.savefig(out_path, dpi=dpi, facecolor=BG_COLOR)
    plt.close()
    print(f"Generated {out_path} (1500x380)")


def check_data_derived():
    """Checks whether real attack graph scores exist, or reports skipped honestly."""
    # Check possible locations for real standalone PageRank scores
    possible_scores = [
        Path("risk/scores.json"),
        Path("graph/pagerank_scores.json"),
        Path("risk/attack_graph_scores.json")
    ]
    found = None
    for p in possible_scores:
        if p.is_file():
            found = p
            break

    if found:
        print(f"Found real scores at {found}, generating attack_graph_scores.png...")
    else:
        print("no real scores found; skipped docs/assets/attack_graph_scores.png (honest reporting)")


if __name__ == "__main__":
    generate_social_preview()
    generate_architecture()
    generate_pipeline_status()
    check_data_derived()
