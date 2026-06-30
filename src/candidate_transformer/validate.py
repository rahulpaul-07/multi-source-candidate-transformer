"""Validation — the output must match the requested schema before we return it.

For the default schema we validate against DEFAULT_SCHEMA. For a custom config
we *derive* a JSON Schema from that very config (types + required), so the
contract the caller asked for is the contract we enforce. Required fields may
not be null; optional fields may be (that's how on_missing="null" stays valid).
"""

from __future__ import annotations

from typing import Any

import jsonschema

_STR = {"type": "string"}
_STR_OR_NULL = {"type": ["string", "null"]}
_NUM_OR_NULL = {"type": ["number", "null"]}

# JSON Schema for the full canonical profile (the default output).
DEFAULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidate_id": _STR,
        "full_name": _STR_OR_NULL,
        "emails": {"type": "array", "items": _STR},
        "phones": {"type": "array", "items": _STR},
        "location": {"type": "object", "properties": {
            "city": _STR_OR_NULL, "region": _STR_OR_NULL, "country": _STR_OR_NULL}},
        "links": {"type": "object", "properties": {
            "linkedin": _STR_OR_NULL, "github": _STR_OR_NULL,
            "portfolio": _STR_OR_NULL, "other": {"type": "array", "items": _STR}}},
        "headline": _STR_OR_NULL,
        "years_experience": _NUM_OR_NULL,
        "skills": {"type": "array", "items": {"type": "object", "properties": {
            "name": _STR, "confidence": {"type": "number"},
            "sources": {"type": "array", "items": _STR}}, "required": ["name"]}},
        "experience": {"type": "array", "items": {"type": "object", "properties": {
            "company": _STR_OR_NULL, "title": _STR_OR_NULL,
            "start": _STR_OR_NULL, "end": _STR_OR_NULL, "summary": _STR_OR_NULL}}},
        "education": {"type": "array", "items": {"type": "object", "properties": {
            "institution": _STR_OR_NULL, "degree": _STR_OR_NULL,
            "field": _STR_OR_NULL, "end_year": {"type": ["integer", "null"]}}}},
        "provenance": {"type": "array", "items": {"type": "object", "properties": {
            "field": _STR, "source": _STR, "method": _STR}}},
        "overall_confidence": {"type": "number"},
    },
    "required": ["candidate_id"],
}

_TYPEMAP = {
    "string": {"type": "string"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "string[]": {"type": "array", "items": {"type": "string"}},
}


def _nullable(schema: dict) -> dict:
    """Allow null in addition to the declared type (for optional fields)."""
    t = schema.get("type")
    if isinstance(t, str):
        return {**schema, "type": [t, "null"]}
    if isinstance(t, list) and "null" not in t:
        return {**schema, "type": t + ["null"]}
    return schema


def schema_from_config(config: dict) -> dict[str, Any]:
    """Build a JSON Schema from a custom output config."""
    props: dict[str, Any] = {}
    required: list[str] = []
    for spec in config["fields"]:
        base = _TYPEMAP.get(spec.get("type"), {})
        if spec.get("required"):
            props[spec["path"]] = base          # required -> may not be null
            required.append(spec["path"])
        else:
            props[spec["path"]] = _nullable(base) if base else {}
    if config.get("include_confidence", True):
        props["overall_confidence"] = {"type": "number"}
    if config.get("include_provenance", True):
        props["provenance"] = {"type": "array"}
    return {"type": "object", "properties": props, "required": required}


def validate_output(obj: dict, config: dict | None = None) -> dict:
    """Validate ``obj`` against the default or config-derived schema.

    Returns the object on success; raises jsonschema.ValidationError otherwise.
    """
    schema = schema_from_config(config) if (config and config.get("fields")) else DEFAULT_SCHEMA
    jsonschema.validate(instance=obj, schema=schema)
    return obj
