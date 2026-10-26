"""
ARGUS Phase 4 - scrubbing layer.

    scrub(record) -> (clean_record, hits)

`hits` is {"presidio_hits": int, "secret_scan_hits": int}. Matches are replaced by
"[REDACTED_<ENTITY>]" markers; the matched text itself is never stored or logged.

Personal-data detection uses Microsoft Presidio's PatternRecognizer classes (fully offline,
no spaCy language model needed, no network). If Presidio cannot be imported, the same regex
patterns run directly (a plain-`re` fallback), so the airlock never silently loses the check.
Secrets are detected with the regex list in patterns.py.
"""

import logging
import re
from dataclasses import dataclass

from privacy.scrubbers.patterns import (
    COMPILED_PII,
    COMPILED_SECRETS,
    PII_SPECS,
    PII_VALIDATORS,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Hit:
    kind: str  # "pii" or "secret"
    entity: str
    start: int
    end: int


_STATE = {"loaded": False, "recognizers": None}


def _load_presidio():
    """Return a list of Presidio PatternRecognizers, or None if Presidio is unavailable."""
    if _STATE["loaded"]:
        return _STATE["recognizers"]
    _STATE["loaded"] = True
    try:
        from presidio_analyzer import Pattern, PatternRecognizer

        recognizers = []
        for entity, regex, _validator, score in PII_SPECS:
            recognizers.append(
                PatternRecognizer(
                    supported_entity=entity,
                    patterns=[Pattern(name=entity.lower() + "_pattern", regex=regex, score=score)],
                    supported_language="en",
                    global_regex_flags=re.MULTILINE,
                )
            )
        _STATE["recognizers"] = recognizers
    except Exception as exc:  # ImportError, or a Presidio/spaCy install problem
        log.warning("Presidio unavailable (%s); using the built-in regex fallback.", exc)
        _STATE["recognizers"] = None
    return _STATE["recognizers"]


def presidio_available():
    return _load_presidio() is not None


def _pii_hits_presidio(text):
    hits = []
    for rec in _load_presidio() or []:
        for res in rec.analyze(text=text, entities=list(rec.supported_entities)):
            entity = res.entity_type
            validator = PII_VALIDATORS.get(entity)
            if validator and not validator(text[res.start:res.end]):
                continue
            hits.append(Hit("pii", entity, res.start, res.end))
    return hits


def _pii_hits_regex(text):
    hits = []
    for entity, rx in COMPILED_PII:
        validator = PII_VALIDATORS.get(entity)
        for m in rx.finditer(text):
            if validator and not validator(m.group(0)):
                continue
            hits.append(Hit("pii", entity, m.start(), m.end()))
    return hits


def _secret_hits(text):
    hits = []
    for name, rx in COMPILED_SECRETS:
        for m in rx.finditer(text):
            hits.append(Hit("secret", name, m.start(), m.end()))
    return hits


def detect(text, engine="auto"):
    """Return every secret / personal-data hit in `text`.

    engine: "auto" (Presidio if available, else regex), "presidio", or "regex".
    """
    if not isinstance(text, str) or not text:
        return []
    if engine == "presidio":
        if not presidio_available():
            raise RuntimeError("Presidio is not available in this environment")
        pii = _pii_hits_presidio(text)
    elif engine == "regex":
        pii = _pii_hits_regex(text)
    else:
        pii = _pii_hits_presidio(text) if presidio_available() else _pii_hits_regex(text)
    return pii + _secret_hits(text)


def _merge(hits):
    """Merge overlapping hits into redaction spans: list of [start, end, entity]."""
    merged = []
    for h in sorted(hits, key=lambda h: (h.start, -h.end)):
        if merged and h.start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], h.end)
            if h.kind == "secret" and merged[-1][3] != "secret":
                merged[-1][2] = h.entity
                merged[-1][3] = "secret"
        else:
            merged.append([h.start, h.end, h.entity, h.kind])
    return merged


def _scrub_text(text, counts, engine):
    hits = detect(text, engine)
    if not hits:
        return text
    counts["presidio_hits"] += sum(1 for h in hits if h.kind == "pii")
    counts["secret_scan_hits"] += sum(1 for h in hits if h.kind == "secret")
    out = text
    for start, end, entity, _kind in reversed(_merge(hits)):
        out = out[:start] + "[REDACTED_" + entity + "]" + out[end:]
    return out


def _scrub_node(node, counts, engine):
    if isinstance(node, dict):
        return {
            _scrub_node(k, counts, engine) if isinstance(k, str) else k: _scrub_node(v, counts, engine)
            for k, v in node.items()
        }
    if isinstance(node, (list, tuple)):
        return [_scrub_node(v, counts, engine) for v in node]
    if isinstance(node, str):
        return _scrub_text(node, counts, engine)
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        as_text = str(node)
        scrubbed = _scrub_text(as_text, counts, engine)
        return node if scrubbed == as_text else scrubbed
    return node


def scrub(record, engine="auto"):
    """Scrub every string (keys and values) in `record`. Returns (clean_record, hits)."""
    counts = {"presidio_hits": 0, "secret_scan_hits": 0}
    clean = _scrub_node(record, counts, engine)
    return clean, counts
