"""Confidence scoring — how sure are we of each value?

Per observation:   base = source_weight x method_factor
Agreement:         independent sources confirming the SAME value combine as
                   1 - prod(1 - c_i)  (more confirmations -> higher confidence)
Disagreement:      a single-value field with conflicting values takes a penalty,
                   so the score honestly reflects the uncertainty.
Overall:           an importance-weighted average (identity fields weigh more).

Directly serves the guiding rule: a value guessed from free text shows up with
low confidence and can never masquerade as certain.
"""

from __future__ import annotations

from collections import defaultdict

from .merge import SCALAR_FIELDS
from .schema import CanonicalProfile, Observation

SOURCE_WEIGHT = {"ats_json": 0.90, "recruiter_csv": 0.85, "github": 0.80, "recruiter_notes": 0.50}
METHOD_FACTOR = {"direct": 1.0, "api": 0.95, "normalized": 0.9, "regex": 0.7, "inferred": 0.5}
DISAGREE_PENALTY = 0.85
CONF_CAP = 0.99

# how much each field counts toward overall_confidence
FIELD_WEIGHT = {"full_name": 2.0, "emails": 2.0, "phones": 1.5,
                "skills": 1.0, "years_experience": 1.0, "headline": 0.5,
                "experience": 1.0, "education": 0.8}
DEFAULT_WEIGHT = 0.7   # location.*, links.*, anything else


def _base(o: Observation) -> float:
    return SOURCE_WEIGHT.get(o.source.value, 0.5) * METHOD_FACTOR.get(o.method.value, 0.5)


def _combine(confs: list[float]) -> float:
    prod = 1.0
    for c in confs:
        prod *= (1.0 - c)
    return min(1.0 - prod, CONF_CAP)


def _get(profile: CanonicalProfile, field: str):
    if "." in field:
        head, leaf = field.split(".", 1)
        return getattr(profile, head).get(leaf)
    return getattr(profile, field)


def score_profile(profile: CanonicalProfile, grouped: dict[str, list[Observation]]) -> CanonicalProfile:
    fc: dict[str, float] = {}

    # single-value fields: confidence of the winning value, penalized on conflict
    for field in SCALAR_FIELDS:
        obs = grouped.get(field) or []
        if not obs:
            continue
        winner = str(_get(profile, field))
        agree = [o for o in obs if str(o.value) == winner]
        conf = _combine([_base(o) for o in agree])
        if len({str(o.value) for o in obs}) > 1:     # conflicting values exist
            conf *= DISAGREE_PENALTY
        fc[field] = round(conf, 3)

    # list fields: score the primary (first) value
    for field in ("emails", "phones"):
        values = getattr(profile, field)
        if not values:
            continue
        primary = values[0]
        agree = [o for o in grouped.get(field, []) if o.value == primary]
        fc[field] = round(_combine([_base(o) for o in agree]), 3)

    # skills: per-skill confidence; field score = average
    by_skill: dict[str, list[Observation]] = defaultdict(list)
    for o in grouped.get("skills", []):
        by_skill[o.value].append(o)
    for sk in profile.skills:
        sk.confidence = round(_combine([_base(o) for o in by_skill.get(sk.name, [])]), 3)
    if profile.skills:
        fc["skills"] = round(sum(s.confidence for s in profile.skills) / len(profile.skills), 3)

    # experience / education: confidence from their contributing observations
    for field in ("experience", "education"):
        obs = grouped.get(field) or []
        if obs:
            fc[field] = round(_combine([_base(o) for o in obs]), 3)

    profile.field_confidence = fc
    profile.overall_confidence = _overall(fc)
    return profile


def _overall(fc: dict[str, float]) -> float:
    num = den = 0.0
    for field, conf in fc.items():
        w = FIELD_WEIGHT.get(field, DEFAULT_WEIGHT)
        num += w * conf
        den += w
    return round(num / den, 3) if den else 0.0
