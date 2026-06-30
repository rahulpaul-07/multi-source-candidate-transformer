"""The extractor contract and a robust dispatcher.

Every source-specific extractor implements ``Extractor``: given a reference
(a file path or a GitHub handle), it returns a list of Observations using
canonical field names. Extractors register themselves in REGISTRY, keyed by
SourceType, so the pipeline can dispatch without knowing concrete classes.

``safe_extract`` is where the *robustness* guarantee lives: a missing or
garbage source is caught here, logged, and turned into an empty result — it
never crashes the run.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from ..schema import Observation, SourceType

log = logging.getLogger("candidate_transformer")

REGISTRY: dict[SourceType, "Extractor"] = {}


class Extractor(ABC):
    source_type: SourceType

    @abstractmethod
    def extract(self, ref: str) -> list[Observation]:
        """Read ``ref`` and return canonical-named Observations."""
        raise NotImplementedError


def register(extractor: "Extractor") -> "Extractor":
    """Register an extractor instance for its source_type."""
    REGISTRY[extractor.source_type] = extractor
    return extractor


def get_extractor(source_type: SourceType) -> Optional["Extractor"]:
    return REGISTRY.get(source_type)


def safe_extract(source_type: SourceType, ref: str) -> list[Observation]:
    """Run the right extractor, degrading gracefully on any failure."""
    extractor = get_extractor(source_type)
    if extractor is None:
        log.warning("no extractor registered for %s (skipping %r)", source_type, ref)
        return []
    try:
        obs = extractor.extract(ref)
        log.info("%s: %d observation(s) from %r", source_type.value, len(obs), ref)
        return obs
    except Exception as exc:  # noqa: BLE001 - robustness: never let one source crash the run
        log.warning("failed to extract %s from %r: %s (skipping)", source_type.value, ref, exc)
        return []
