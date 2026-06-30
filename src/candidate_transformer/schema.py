"""Core data types: the Observation intermediate representation and the
canonical profile (our internal record + the default output shape).

Two ideas drive this module:

1.  **Observation** is the single, uniform shape that *every* source is
    converted into during extraction. After extraction nothing downstream
    needs to know whether a value came from a CSV, a JSON blob, free text,
    or an API — it only sees Observations. This is what keeps merge,
    scoring and projection completely source-agnostic.

2.  The **CanonicalProfile** is the full internal record. Every value keeps
    its provenance (where it came from) and a confidence (how sure we are).
    The clean, public JSON is produced only at projection time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Enumerations                                                                  #
# --------------------------------------------------------------------------- #
class SourceType(str, Enum):
    """The kinds of input we know how to read."""
    RECRUITER_CSV = "recruiter_csv"      # structured rows
    ATS_JSON = "ats_json"                # structured, foreign field names
    RECRUITER_NOTES = "recruiter_notes"  # unstructured free text
    GITHUB = "github"                    # unstructured, from a public API


class Method(str, Enum):
    """How a value was obtained — feeds the confidence score.

    DIRECT  : read straight from a structured field   (most trusted)
    API     : returned by a structured API            (trusted)
    REGEX   : pattern-matched out of free text         (less trusted)
    INFERRED: derived/guessed (e.g. unknown skill kept) (least trusted)
    NORMALIZED: value was reshaped into a standard format
    """
    DIRECT = "direct"
    API = "api"
    REGEX = "regex"
    INFERRED = "inferred"
    NORMALIZED = "normalized"


# --------------------------------------------------------------------------- #
# Provenance + the Observation intermediate representation                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Provenance:
    """A paper-trail entry: which source produced a value, and how."""
    field: str
    source: str   # SourceType value
    method: str   # Method value

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "source": self.source, "method": self.method}


@dataclass
class Observation:
    """One fact extracted from one source, in a uniform shape.

    ``field`` uses canonical names (e.g. "emails", "full_name") so that the
    merge stage can group observations across sources without translation.
    """
    field: str            # canonical field name this observation targets
    value: Any            # the (not-yet-normalized) value
    source: SourceType    # which source it came from
    method: Method        # how it was obtained
    raw: Any = None       # original raw value, kept for traceability/debugging

    def provenance(self) -> Provenance:
        return Provenance(field=self.field, source=self.source.value,
                          method=self.method.value)


# --------------------------------------------------------------------------- #
# Sub-objects of the canonical profile                                          #
# --------------------------------------------------------------------------- #
@dataclass
class Skill:
    name: str
    confidence: float
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "confidence": round(self.confidence, 3),
                "sources": list(self.sources)}


@dataclass
class Experience:
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None   # YYYY-MM
    end: Optional[str] = None     # YYYY-MM or None (= current)
    summary: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"company": self.company, "title": self.title,
                "start": self.start, "end": self.end, "summary": self.summary}


@dataclass
class Education:
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {"institution": self.institution, "degree": self.degree,
                "field": self.field, "end_year": self.end_year}


# --------------------------------------------------------------------------- #
# The canonical profile (internal record + default output shape)               #
# --------------------------------------------------------------------------- #
@dataclass
class CanonicalProfile:
    """The full internal record for one candidate.

    Scalar/list values are the clean canonical values. ``field_confidence``
    and ``provenance`` carry the per-field trust metadata that the projection
    layer can include or omit on request.
    """
    candidate_id: str = ""
    full_name: Optional[str] = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    location: dict[str, Optional[str]] = field(
        default_factory=lambda: {"city": None, "region": None, "country": None})
    links: dict[str, Any] = field(
        default_factory=lambda: {"linkedin": None, "github": None,
                                 "portfolio": None, "other": []})
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[Skill] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)

    # trust metadata
    provenance: list[Provenance] = field(default_factory=list)
    field_confidence: dict[str, float] = field(default_factory=dict)
    overall_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Render the full default-schema JSON for this profile."""
        return {
            "candidate_id": self.candidate_id,
            "full_name": self.full_name,
            "emails": list(self.emails),
            "phones": list(self.phones),
            "location": dict(self.location),
            "links": {**self.links, "other": list(self.links.get("other", []))},
            "headline": self.headline,
            "years_experience": self.years_experience,
            "skills": [s.to_dict() for s in self.skills],
            "experience": [e.to_dict() for e in self.experience],
            "education": [e.to_dict() for e in self.education],
            "provenance": [p.to_dict() for p in self.provenance],
            "overall_confidence": round(self.overall_confidence, 3),
        }
