"""Source detection: decide which kind of input a reference points to.

Detection is deterministic and based on the reference string (extension or a
GitHub marker) with a content-sniff fallback for files without a clear suffix.
Unknown inputs return ``None`` so the caller can skip them instead of crashing.
"""

from __future__ import annotations

import os
from typing import Optional

from .schema import SourceType


def detect_source_type(ref: str) -> Optional[SourceType]:
    """Return the SourceType for a reference (file path or GitHub handle/URL)."""
    if not ref or not isinstance(ref, str):
        return None
    r = ref.strip().lower()

    # GitHub is checked first: a GitHub fixture is also JSON, so order matters.
    if "github.com/" in r or r.startswith("github:") or r.endswith(".github.json"):
        return SourceType.GITHUB
    if r.endswith(".csv"):
        return SourceType.RECRUITER_CSV
    if r.endswith(".json"):
        return SourceType.ATS_JSON
    if r.endswith(".txt"):
        return SourceType.RECRUITER_NOTES

    return _sniff_content(ref)


def _sniff_content(path: str) -> Optional[SourceType]:
    """Best-effort fallback for files without a recognized extension."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(2048).lstrip()
    except OSError:
        return None
    if not head:
        return None
    if head[0] in "{[":
        return SourceType.ATS_JSON
    if "," in head.splitlines()[0]:
        return SourceType.RECRUITER_CSV
    return SourceType.RECRUITER_NOTES
