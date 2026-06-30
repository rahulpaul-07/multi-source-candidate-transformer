"""Merge: turn many source records into one canonical profile per candidate.

Three jobs:
  1. Identity resolution  - which records are the same person? (union-find over
     blocking keys: email, name+phone, name+handle). Name alone never merges.
  2. Conflict resolution  - for single-value fields, pick a winner by source
     reliability (structured > GitHub > notes), with a deterministic tie-break.
  3. Assembly             - union+dedupe list fields; match list-of-objects
     (experience/education) by key and merge field-wise; record provenance.

Confidence numbers are filled in by the confidence stage; here we build the
structure and the paper trail.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Optional

from .schema import (CanonicalProfile, Education, Experience, Observation,
                     Provenance, Skill, SourceRecord, SourceType)

# higher = more reliable for single-value FACTS (skills are unioned, not ranked)
SOURCE_RANK = {
    SourceType.ATS_JSON.value: 3,
    SourceType.RECRUITER_CSV.value: 3,
    SourceType.GITHUB.value: 2,
    SourceType.RECRUITER_NOTES.value: 1,
}
METHOD_RANK = {"direct": 3, "api": 3, "normalized": 2, "regex": 2, "inferred": 1}
# fixed order for deterministic tie-breaks (no randomness, ever)
SOURCE_ORDER = [SourceType.ATS_JSON.value, SourceType.RECRUITER_CSV.value,
                SourceType.GITHUB.value, SourceType.RECRUITER_NOTES.value]

SCALAR_FIELDS = ["full_name", "headline", "years_experience",
                 "location.city", "location.region", "location.country",
                 "links.linkedin", "links.github", "links.portfolio"]

_GH = re.compile(r"github\.com/([A-Za-z0-9-]+)", re.I)


def _handle(url: str) -> Optional[str]:
    m = _GH.search(str(url))
    return m.group(1).lower() if m else None


# --------------------------------------------------------------------------- #
# 1. Identity resolution (union-find + blocking)                               #
# --------------------------------------------------------------------------- #
class _DSU:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)   # keep smaller root -> deterministic


def resolve_identities(records: list[SourceRecord]) -> list[list[SourceRecord]]:
    dsu = _DSU(len(records))
    by_email: dict[str, list[int]] = defaultdict(list)
    by_name_phone: dict[tuple, list[int]] = defaultdict(list)
    by_name_handle: dict[tuple, list[int]] = defaultdict(list)

    for i, rec in enumerate(records):
        names, emails, phones, handles = set(), set(), set(), set()
        for o in rec.observations:
            if o.field == "full_name":
                names.add(str(o.value).lower())
            elif o.field == "emails":
                emails.add(o.value)
            elif o.field == "phones":
                phones.add(o.value)
            elif o.field == "links.github":
                h = _handle(o.value)
                if h:
                    handles.add(h)
        for e in emails:
            by_email[e].append(i)
        for nm in names:
            for ph in phones:
                by_name_phone[(nm, ph)].append(i)
            for h in handles:
                by_name_handle[(nm, h)].append(i)

    for groups in (by_email, by_name_phone, by_name_handle):
        for idxs in groups.values():
            for j in idxs[1:]:
                dsu.union(idxs[0], j)

    clusters: dict[int, list[SourceRecord]] = defaultdict(list)
    for i, rec in enumerate(records):
        clusters[dsu.find(i)].append(rec)
    # stable order: by smallest original index in each cluster
    return [clusters[k] for k in sorted(clusters)]


# --------------------------------------------------------------------------- #
# 2 + 3. Merge one cluster into a canonical profile                             #
# --------------------------------------------------------------------------- #
def _rank(o: Observation) -> tuple:
    return (SOURCE_RANK.get(o.source.value, 0), METHOD_RANK.get(o.method.value, 0))


def _winner(obs: list[Observation]) -> Observation:
    # highest (source_rank, method_rank); tie-break: fixed source order, then value
    return min(obs, key=lambda o: (-_rank(o)[0], -_rank(o)[1],
                                   SOURCE_ORDER.index(o.source.value)
                                   if o.source.value in SOURCE_ORDER else 99,
                                   str(o.value)))


def _set_dotted(profile: CanonicalProfile, field: str, value: Any) -> None:
    if "." in field:
        head, leaf = field.split(".", 1)
        getattr(profile, head)[leaf] = value
    else:
        setattr(profile, field, value)


def _union_values(obs: list[Observation]) -> list[str]:
    best: dict[str, int] = {}
    for o in obs:
        r = SOURCE_RANK.get(o.source.value, 0)
        best[o.value] = max(best.get(o.value, -1), r)
    return [v for v, _ in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))]


def _merge_objects(obs: list[Observation], key_fn, build_fn) -> list:
    groups: dict[Any, list[Observation]] = {}
    order: list[Any] = []
    for o in obs:
        if not isinstance(o.value, dict):
            continue
        k = key_fn(o.value)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(o)
    return [build_fn(groups[k]) for k in order]


def _exp_key(v: dict) -> tuple:
    return ((v.get("company") or "").strip().lower(), (v.get("start") or ""))


def _ordered(obs: list[Observation]) -> list[Observation]:
    # reliable sources first; fully deterministic tie-break (no input-order dependence)
    return sorted(obs, key=lambda o: (-_rank(o)[0], -_rank(o)[1],
                                      SOURCE_ORDER.index(o.source.value)
                                      if o.source.value in SOURCE_ORDER else 99,
                                      str(o.value)))


def _build_exp(obs: list[Observation]) -> Experience:
    ordered = _ordered(obs)
    def pick(field):
        for o in ordered:
            val = o.value.get(field)
            if val:
                return val
        return None
    return Experience(company=pick("company"), title=pick("title"),
                      start=pick("start"), end=pick("end"), summary=pick("summary"))


def _edu_key(v: dict) -> tuple:
    return ((v.get("institution") or "").strip().lower(),
            (v.get("degree") or "").strip().lower())


def _build_edu(obs: list[Observation]) -> Education:
    ordered = _ordered(obs)
    def pick(field):
        for o in ordered:
            val = o.value.get(field)
            if val:
                return val
        return None
    return Education(institution=pick("institution"), degree=pick("degree"),
                     field=pick("field"), end_year=pick("end_year"))


def merge_cluster(records: list[SourceRecord]) -> tuple[CanonicalProfile, dict[str, list[Observation]]]:
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for rec in records:
        for o in rec.observations:
            grouped[o.field].append(o)

    profile = CanonicalProfile()

    for f in SCALAR_FIELDS:
        if grouped.get(f):
            _set_dotted(profile, f, _winner(grouped[f]).value)

    profile.emails = _union_values(grouped.get("emails", []))
    profile.phones = _union_values(grouped.get("phones", []))
    if grouped.get("links.other"):
        profile.links["other"] = _union_values(grouped["links.other"])

    # skills: dedupe by canonical name, collect contributing sources
    skill_sources: dict[str, set] = defaultdict(set)
    for o in grouped.get("skills", []):
        skill_sources[o.value].add(o.source.value)
    profile.skills = [Skill(name=n, confidence=0.0, sources=sorted(skill_sources[n]))
                      for n in sorted(skill_sources)]

    profile.experience = sorted(
        _merge_objects(grouped.get("experience", []), _exp_key, _build_exp),
        key=lambda e: ((e.start or ""), (e.company or "").lower(), (e.title or "").lower()))
    profile.education = sorted(
        _merge_objects(grouped.get("education", []), _edu_key, _build_edu),
        key=lambda e: ((e.institution or "").lower(), (e.degree or "").lower(),
                       e.end_year or 0))

    # provenance: one entry per (field, source, method), sorted for determinism
    prov = {(f, o.source.value, o.method.value)
            for f, obs in grouped.items() for o in obs}
    profile.provenance = [Provenance(*p) for p in sorted(prov)]

    profile.candidate_id = _candidate_id(profile)
    return profile, grouped


def _candidate_id(profile: CanonicalProfile) -> str:
    key = profile.emails[0] if profile.emails else (profile.full_name or "unknown").lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
