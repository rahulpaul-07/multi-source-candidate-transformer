"""Recruiter notes extractor — free text, our first unstructured source.

We pull only high-precision signals (emails, phones, "N years", labelled
name/skills) with regex, and do a conservative keyword scan for skills. Every
value is tagged REGEX or INFERRED, never DIRECT — so the confidence stage keeps
free-text facts below structured ones, and they can never override them. When in
doubt we extract nothing: wrong-but-confident is worse than honestly-empty.
"""

from __future__ import annotations

import re

from ..schema import Method, Observation, SourceRecord, SourceType
from .base import Extractor, register

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\w)(\+?\d[\d\s().\-]{6,}\d)(?!\w)")
_YEARS = re.compile(r"(\d{1,2})\+?\s*(?:years?|yrs?)\b", re.I)
_NAME_LBL = re.compile(r"^\s*(?:name|candidate)\s*[:\-]\s*(.+)$", re.I | re.M)
_SKILLS_LBL = re.compile(r"^\s*skills?\s*[:\-]\s*(.+)$", re.I | re.M)

# conservative vocabulary for inline skill mentions (canonicalized later)
_SKILL_VOCAB = {
    "python", "java", "javascript", "js", "typescript", "ts", "react", "node",
    "node.js", "nodejs", "django", "flask", "fastapi", "kubernetes", "k8s",
    "docker", "aws", "gcp", "azure", "go", "golang", "rust", "c++", "sql",
    "postgres", "postgresql", "mongodb", "redis", "kafka", "spark", "tensorflow",
    "pytorch", "graphql",
}


class NotesExtractor(Extractor):
    source_type = SourceType.RECRUITER_NOTES

    def extract(self, ref: str) -> list[SourceRecord]:
        with open(ref, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if not text.strip():
            return []
        rec = SourceRecord(source=self.source_type)
        seen: set[tuple[str, str]] = set()

        def add(field: str, value, method: Method, raw=None):
            key = (field, str(value).lower())
            if key in seen:
                return
            seen.add(key)
            rec.observations.append(Observation(field=field, value=value,
                                                source=self.source_type, method=method, raw=raw))

        for m in _EMAIL.findall(text):
            add("emails", m.strip(), Method.REGEX)
        for m in _PHONE.findall(text):
            if sum(ch.isdigit() for ch in m) >= 7:        # avoid catching IDs/dates
                add("phones", m.strip(), Method.REGEX)

        ylist = _YEARS.findall(text)
        if ylist:
            add("years_experience", float(max(int(y) for y in ylist)), Method.REGEX)

        nm = _NAME_LBL.search(text)
        if nm:
            add("full_name", nm.group(1).strip(), Method.REGEX)

        sm = _SKILLS_LBL.search(text)
        if sm:
            for sk in re.split(r"[,/;]| and ", sm.group(1)):
                if sk.strip():
                    add("skills", sk.strip(), Method.REGEX)

        # conservative inline skill scan (lower trust: INFERRED)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9.+#]*", text):
            clean = token.rstrip(".")          # drop sentence punctuation, keep node.js / c++
            if clean.lower() in _SKILL_VOCAB:
                add("skills", clean, Method.INFERRED)

        return [rec] if rec.observations else []


register(NotesExtractor())
