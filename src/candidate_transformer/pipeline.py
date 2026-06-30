"""End-to-end orchestration: detect -> extract -> normalize -> merge -> score
-> project -> validate, over any number of inputs.

Robust by construction: an unrecognized or garbage input is logged and skipped,
never fatal. Output order is deterministic (sorted by candidate_id) regardless
of the order inputs were supplied in.
"""

from __future__ import annotations

import logging

from . import extractors  # noqa: F401  (importing registers all extractors)
from .confidence import score_profile
from .detect import detect_source_type
from .extractors.base import safe_extract
from .merge import merge_cluster, resolve_identities
from .normalize import normalize_records
from .projection import project
from .schema import SourceRecord
from .validate import validate_output

log = logging.getLogger("candidate_transformer")


def collect_records(inputs: list[str]) -> list[SourceRecord]:
    """Detect and extract every input, skipping anything unrecognized/broken."""
    records: list[SourceRecord] = []
    for ref in inputs:
        source_type = detect_source_type(ref)
        if source_type is None:
            log.warning("unrecognized input, skipping: %r", ref)
            continue
        records.extend(safe_extract(source_type, ref))
    return records


def run_pipeline(inputs: list[str], config: dict | None = None) -> list[dict]:
    """Run the full pipeline and return one validated output dict per candidate."""
    records = normalize_records(collect_records(inputs))

    # merge + score first, so we can order candidates deterministically by id
    scored = []
    for cluster in resolve_identities(records):
        profile, grouped = merge_cluster(cluster)
        score_profile(profile, grouped)
        scored.append(profile)
    scored.sort(key=lambda p: p.candidate_id)

    results: list[dict] = []
    for profile in scored:
        output = project(profile, config)
        validate_output(output, config)        # never return invalid output
        results.append(output)
    return results
