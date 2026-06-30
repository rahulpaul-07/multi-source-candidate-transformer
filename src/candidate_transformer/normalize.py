"""Normalization: force every value into one canonical format.

Runs *before* merge — on purpose. Once "(555) 123-4567" and "+1 555 123 4567"
both become "+15551234567", the merge stage sees them as the SAME value (so
they corroborate and raise confidence) instead of a false conflict.

Invalid values (an unparseable phone, a junk email) are dropped rather than
guessed — wrong-but-confident is worse than honestly-empty.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import phonenumbers
import pycountry

from .schema import Observation, SourceRecord

# --------------------------------------------------------------------------- #
# Skills                                                                        #
# --------------------------------------------------------------------------- #
_SKILL_ALIASES = {
    "js": "JavaScript", "javascript": "JavaScript", "java script": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python",
    "go": "Go", "golang": "Go",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "node": "Node.js", "node.js": "Node.js", "nodejs": "Node.js",
    "react": "React", "reactjs": "React", "react.js": "React",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "aws": "AWS", "gcp": "Google Cloud", "azure": "Azure",
    "c++": "C++", "c#": "C#", "graphql": "GraphQL",
    "tf": "TensorFlow", "tensorflow": "TensorFlow", "pytorch": "PyTorch",
    "sql": "SQL", "docker": "Docker", "kafka": "Kafka", "spark": "Spark",
    "rust": "Rust", "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "mongodb": "MongoDB", "redis": "Redis", "shell": "Shell", "bash": "Shell",
}


def canonical_skill(value: str) -> str:
    """Map a skill to its canonical name; unknown skills are kept (trimmed)."""
    key = str(value).strip().lower()
    return _SKILL_ALIASES.get(key, str(value).strip())


# --------------------------------------------------------------------------- #
# Phones / emails / names                                                       #
# --------------------------------------------------------------------------- #
def normalize_phone(value: Any, region: str = "US") -> Optional[str]:
    """To E.164, e.g. '+15551234567'. Returns None if not a valid number.

    If there is no country code we parse with ``region`` (default US, a
    documented assumption); a candidate's own country overrides it when known.
    """
    s = str(value).strip()
    try:
        num = phonenumbers.parse(s, None if s.startswith("+") else region)
    except phonenumbers.NumberParseException:
        return None
    # Accept structurally *possible* numbers (correct length for the region) and
    # reject impossible ones. Strict is_valid_number() over-rejects fictional and
    # newly-assigned ranges, which would drop legitimate data — too lossy here.
    if phonenumbers.is_possible_number(num):
        return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    return None


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def normalize_email(value: Any) -> Optional[str]:
    s = str(value).strip().lower()
    return s if _EMAIL_RE.match(s) else None


def normalize_name(value: Any) -> Optional[str]:
    s = " ".join(str(value).split()).strip()   # collapse whitespace, keep original case
    return s or None


# --------------------------------------------------------------------------- #
# Country (ISO-3166 alpha-2) and dates (YYYY-MM)                                #
# --------------------------------------------------------------------------- #
_COUNTRY_ALIASES = {
    "usa": "US", "u.s.a.": "US", "u.s.": "US", "united states": "US",
    "uk": "GB", "u.k.": "GB", "great britain": "GB", "england": "GB",
    "uae": "AE", "south korea": "KR", "north korea": "KP", "russia": "RU",
}


def normalize_country(value: Any) -> Optional[str]:
    s = str(value).strip()
    if not s:
        return None
    if s.lower() in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[s.lower()]
    try:
        return pycountry.countries.lookup(s).alpha_2
    except LookupError:
        return None


_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
_CURRENT = {"present", "current", "now", "ongoing", "till date", "to date"}


def normalize_date(value: Any) -> Optional[str]:
    """To 'YYYY-MM' (or 'YYYY' if only a year is known — we don't invent a month).

    'Present'/'current' returns None (meaning an open-ended/current role).
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in _CURRENT:
        return None
    m = re.match(r"^(\d{4})[-/](\d{1,2})", s)          # 2020-06, 2020/6, 2020-06-01
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{1,2})[-/](\d{4})$", s)          # 06/2020
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.match(r"^([A-Za-z]{3,})[ ,]+(\d{4})$", s)    # Jan 2020 / January 2020
    if m and m.group(1)[:3].lower() in _MONTHS:
        return f"{m.group(2)}-{_MONTHS[m.group(1)[:3].lower()]:02d}"
    m = re.match(r"^(\d{4})$", s)                       # year only
    if m:
        return m.group(1)
    return None


# --------------------------------------------------------------------------- #
# Apply normalization to a whole record                                         #
# --------------------------------------------------------------------------- #
def _region_hint(rec: SourceRecord) -> str:
    for o in rec.observations:
        if o.field == "location.country":
            cc = normalize_country(o.value)
            if cc:
                return cc
    return "US"   # documented default when the candidate's country is unknown


def _normalize_value(field: str, value: Any, region: str) -> Any:
    if field == "emails":
        return normalize_email(value)
    if field == "phones":
        return normalize_phone(value, region)
    if field == "skills":
        return canonical_skill(value)
    if field in ("full_name", "headline"):
        return normalize_name(value)
    if field == "location.country":
        return normalize_country(value)
    if field == "years_experience":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if field == "experience" and isinstance(value, dict):
        v = dict(value)
        v["start"] = normalize_date(v.get("start"))
        v["end"] = normalize_date(v.get("end"))
        for k in ("company", "title", "summary"):
            if v.get(k):
                v[k] = str(v[k]).strip()
        return v if (v.get("company") or v.get("title")) else None
    if field == "education" and isinstance(value, dict):
        v = dict(value)
        try:
            v["end_year"] = int(v["end_year"]) if v.get("end_year") not in (None, "") else None
        except (TypeError, ValueError):
            v["end_year"] = None
        for k in ("institution", "degree", "field"):
            if v.get(k):
                v[k] = str(v[k]).strip()
        return v if (v.get("institution") or v.get("degree")) else None
    # default: trim strings, pass through others
    return str(value).strip() if isinstance(value, str) else value


def normalize_records(records: list[SourceRecord]) -> list[SourceRecord]:
    """Return records with every observation value normalized; drop invalids."""
    out: list[SourceRecord] = []
    for rec in records:
        region = _region_hint(rec)
        norm = SourceRecord(source=rec.source)
        for o in rec.observations:
            nv = _normalize_value(o.field, o.value, region)
            if nv is None or nv == "":
                continue   # invalid/empty -> drop, never guess
            norm.observations.append(Observation(
                field=o.field, value=nv, source=o.source, method=o.method, raw=o.raw))
        out.append(norm)
    return out
