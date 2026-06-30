"""ATS JSON extractor — the source whose field names do NOT match ours.

The whole job here is *remapping*: the ATS calls things "primary_email",
"work_history", "qualification"; we translate every one of those into our
canonical field names so the rest of the pipeline never sees foreign keys.

Remapping is declarative (see the alias tables): each canonical target lists
the foreign paths it may live under, tried in order. Dotted canonical names
like "location.city" are scalar sub-fields; the merge/assembly stage knows how
to nest them.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..schema import Method, Observation, SourceRecord, SourceType
from .base import Extractor, register

# canonical (possibly dotted) field  ->  foreign paths to try, in order
_SCALAR_ALIASES: dict[str, list[str]] = {
    "full_name": ["full_name", "name", "candidate_name"],
    "emails": ["contact.primary_email", "primary_email", "email", "email_address", "contact.email"],
    "phones": ["contact.mobile_number", "mobile_number", "phone", "mobile", "contact.phone"],
    "location.city": ["city", "location.city", "address.city"],
    "location.region": ["state", "region", "location.region", "address.state"],
    "location.country": ["country", "location.country", "address.country"],
    "links.linkedin": ["social.linkedin_url", "linkedin_url", "linkedin"],
    "links.github": ["social.github_url", "github_url", "github"],
    "headline": ["headline", "summary", "job_title"],
}
_SKILL_KEYS = ["skills", "skill_set", "technologies", "tech_stack"]
_WORK_KEYS = ["work_history", "experience", "employment_history", "positions"]
_EDU_KEYS = ["education", "schools", "academics"]


def _resolve(obj: dict, path: str) -> Any:
    """Resolve a dotted path inside a nested dict; return None if absent."""
    cur: Any = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _first(obj: dict, paths: list[str]) -> Any:
    for p in paths:
        v = _resolve(obj, p)
        if v not in (None, "", []):
            return v
    return None


def _first_key(obj: dict, keys: list[str]) -> Any:
    for k in keys:
        if k in obj and obj[k] not in (None, "", []):
            return obj[k]
    return None


class ATSJSONExtractor(Extractor):
    source_type = SourceType.ATS_JSON

    def extract(self, ref: str) -> list[SourceRecord]:
        with open(ref, encoding="utf-8") as fh:
            data = json.load(fh)               # malformed JSON -> caught by safe_extract
        return [self._candidate_to_record(c) for c in self._iter_candidates(data)]

    def _iter_candidates(self, data: Any) -> list[dict]:
        if isinstance(data, list):
            return [c for c in data if isinstance(c, dict)]
        if isinstance(data, dict):
            for key in ("candidates", "applicants", "results", "records"):
                if isinstance(data.get(key), list):
                    return [c for c in data[key] if isinstance(c, dict)]
            return [data]                       # a single candidate object
        return []

    def _candidate_to_record(self, c: dict) -> SourceRecord:
        rec = SourceRecord(source=self.source_type)
        add = lambda f, v, raw=None: rec.observations.append(Observation(
            field=f, value=v, source=self.source_type, method=Method.DIRECT, raw=raw))

        # scalar / simple-list fields via the alias table
        for target, paths in _SCALAR_ALIASES.items():
            val = _first(c, paths)
            if val is not None:
                add(target, str(val).strip() if isinstance(val, str) else val, val)

        # full_name fallback: first_name + last_name
        if _first(c, _SCALAR_ALIASES["full_name"]) is None:
            fn, ln = c.get("first_name"), c.get("last_name")
            if fn or ln:
                add("full_name", " ".join(p for p in (fn, ln) if p).strip(), {"first": fn, "last": ln})

        # skills (each becomes its own observation)
        skills = _first_key(c, _SKILL_KEYS) or []
        if isinstance(skills, list):
            for sk in skills:
                if isinstance(sk, str) and sk.strip():
                    add("skills", sk.strip(), sk)

        # current role from employer + job_title (merge dedupes against work_history)
        employer, job_title = c.get("employer"), c.get("job_title")
        if employer or job_title:
            add("experience", {"company": employer, "title": job_title, "end": None},
                {"employer": employer, "job_title": job_title})

        # work history -> experience entries (remap foreign keys)
        for w in (_first_key(c, _WORK_KEYS) or []):
            if isinstance(w, dict):
                add("experience", {
                    "company": w.get("org") or w.get("company") or w.get("employer"),
                    "title": w.get("position") or w.get("title") or w.get("role"),
                    "start": w.get("from") or w.get("start"),
                    "end": w.get("to") or w.get("end"),
                    "summary": w.get("summary") or w.get("description"),
                }, w)

        # education -> education entries (remap foreign keys)
        for e in (_first_key(c, _EDU_KEYS) or []):
            if isinstance(e, dict):
                add("education", {
                    "institution": e.get("school") or e.get("institution"),
                    "degree": e.get("qualification") or e.get("degree"),
                    "field": e.get("major") or e.get("field"),
                    "end_year": e.get("graduated") or e.get("end_year"),
                }, e)

        return rec


register(ATSJSONExtractor())
