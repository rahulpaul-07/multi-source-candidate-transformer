"""Projection — render the canonical record into a config-requested shape.

This is the "configurable output" twist. The engine always builds the full
internal CanonicalProfile; this layer is a separate, stateless view over it.
It only READS the record (via to_dict()) — it never re-extracts or recomputes,
so the exact same engine serves the default schema and every custom config.

A config field spec:  {path, from?, type?, required?, normalize?}
  path      : output key
  from      : canonical source path (defaults to `path`); supports dotted keys,
              array index (emails[0]) and array-map (skills[].name)
  normalize : "E164" | "canonical"  (applied to the projected value)
  type      : "string" | "string[]" | "number" | "boolean"
Top-level: include_confidence, include_provenance, on_missing (null|omit|error).
"""

from __future__ import annotations

import re
from typing import Any

from .normalize import canonical_skill, normalize_phone
from .schema import CanonicalProfile

_SEG = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\[(\d*)\])?$")


def _resolve(data: Any, path: str) -> tuple[Any, bool]:
    """Resolve a canonical path; return (value, found)."""
    if path == "":
        return data, True
    seg, _, rest = path.partition(".")
    m = _SEG.match(seg)
    if not m:
        return None, False
    name, bracket, idx = m.group(1), m.group(2), m.group(3)
    if not isinstance(data, dict) or name not in data:
        return None, False
    val = data[name]
    if bracket is None:                      # plain key
        return _resolve(val, rest)
    if idx == "":                            # [] -> map over the list
        if not isinstance(val, list):
            return None, False
        out = []
        for item in val:
            v, found = _resolve(item, rest)
            if found and v is not None:
                out.append(v)
        return out, True
    i = int(idx)                             # [n] -> index
    if not isinstance(val, list) or i >= len(val):
        return None, False
    return _resolve(val[i], rest)


def _apply_normalize(value: Any, kind: str | None) -> Any:
    if kind is None:
        return value
    fn = {"E164": lambda v: normalize_phone(v) or v,
          "canonical": canonical_skill}.get(kind)
    if fn is None:
        return value
    return [fn(v) for v in value] if isinstance(value, list) else fn(value)


def _coerce(value: Any, type_name: str | None) -> Any:
    if type_name is None or value is None:
        return value
    if type_name == "string":
        return str(value)
    if type_name == "string[]":
        return [str(v) for v in (value if isinstance(value, list) else [value])]
    if type_name == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if type_name == "boolean":
        return bool(value)
    return value


class MissingFieldError(KeyError):
    """Raised when a value is missing and on_missing == 'error'."""


def project(profile: CanonicalProfile, config: dict | None = None) -> dict:
    data = profile.to_dict()
    config = config or {}
    inc_conf = config.get("include_confidence", True)
    inc_prov = config.get("include_provenance", True)

    if not config.get("fields"):                      # default schema (honor toggles)
        out = data
        if not inc_conf:
            out.pop("overall_confidence", None)
            for s in out.get("skills", []):
                s.pop("confidence", None)
        if not inc_prov:
            out.pop("provenance", None)
        return out

    on_missing = config.get("on_missing", "null")
    out: dict[str, Any] = {}
    for spec in config["fields"]:
        path = spec["path"]
        value, found = _resolve(data, spec.get("from", path))
        if found and value not in (None, [], ""):
            value = _coerce(_apply_normalize(value, spec.get("normalize")), spec.get("type"))
            out[path] = value
        elif on_missing == "omit":
            continue
        elif on_missing == "error":
            raise MissingFieldError(f"required field {path!r} is missing")
        else:                                          # "null"
            out[path] = None

    if inc_conf:
        out["overall_confidence"] = data["overall_confidence"]
    if inc_prov:
        out["provenance"] = data["provenance"]
    return out
