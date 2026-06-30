"""Recruiter CSV extractor.

Reads structured rows (name, email, phone, current_company, title) and emits
one SourceRecord per row. Column headers are matched case/spacing-insensitively
so small header variations ("Full Name", "email address") still work. Values
are only trimmed here — formatting (E.164, etc.) happens in the normalize stage.
"""

from __future__ import annotations

import csv
from typing import Optional

from ..schema import Method, Observation, SourceRecord, SourceType
from .base import Extractor, register

# header alias -> canonical target
_HEADER_ALIASES = {
    "name": "full_name", "full name": "full_name", "fullname": "full_name",
    "candidate": "full_name", "candidate name": "full_name",
    "email": "emails", "email address": "emails", "e-mail": "emails",
    "phone": "phones", "phone number": "phones", "mobile": "phones", "tel": "phones",
    "current company": "company", "current_company": "company", "company": "company",
    "employer": "company",
    "title": "title", "job title": "title", "role": "title", "position": "title",
}


def _norm_header(h: str) -> str:
    return " ".join(h.strip().lower().replace("_", " ").split())


class CSVExtractor(Extractor):
    source_type = SourceType.RECRUITER_CSV

    def extract(self, ref: str) -> list[SourceRecord]:
        records: list[SourceRecord] = []
        with open(ref, newline="", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return records  # empty file -> no records
            # map each real header to a canonical target once
            targets = {col: _HEADER_ALIASES.get(_norm_header(col)) for col in reader.fieldnames}
            for row in reader:
                rec = self._row_to_record(row, targets)
                if rec.observations:        # skip fully empty rows
                    records.append(rec)
        return records

    def _row_to_record(self, row: dict, targets: dict[str, Optional[str]]) -> SourceRecord:
        rec = SourceRecord(source=self.source_type)
        company = title = None
        for col, target in targets.items():
            if target is None:
                continue
            value = (row.get(col) or "").strip()
            if not value:
                continue
            if target in ("full_name", "emails", "phones"):
                rec.observations.append(Observation(
                    field=target, value=value, source=self.source_type,
                    method=Method.DIRECT, raw=row.get(col)))
            elif target == "company":
                company = value
            elif target == "title":
                title = value
        # current_company + title together describe the candidate's current role
        if company or title:
            rec.observations.append(Observation(
                field="experience",
                value={"company": company, "title": title, "end": None},
                source=self.source_type, method=Method.DIRECT,
                raw={"company": company, "title": title}))
        return rec


register(CSVExtractor())
