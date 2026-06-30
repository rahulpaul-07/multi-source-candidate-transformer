import json

import jsonschema
import pytest

from candidate_transformer.pipeline import run_pipeline
from candidate_transformer.projection import MissingFieldError


def _by_name(results):
    return {r["full_name"]: r for r in results}


def test_four_candidates_and_garbage_skipped(sample_inputs):
    results = run_pipeline(sample_inputs)              # includes a malformed source
    assert len(results) == 4                           # broken source skipped, run survives


def test_transitive_identity_merge(sample_inputs):
    rob = _by_name(run_pipeline(sample_inputs))["Robert Smith"]
    # CSV+ATS by email, notes by name+phone, GitHub by name+handle -> one person
    assert set(rob["emails"]) == {"robert@acme.com", "bob.smith@gmail.com"}
    assert rob["phones"] == ["+15551234567"]           # corroborated, single value
    assert rob["links"]["github"] == "https://github.com/robsmith"


def test_no_false_merge_on_name_alone(sample_inputs):
    names = [r["full_name"] for r in run_pipeline(sample_inputs)]
    assert "Bob Smith" in names and "Robert Smith" in names   # not merged together


def test_confidence_reflects_evidence(sample_inputs):
    rob = _by_name(run_pipeline(sample_inputs))["Robert Smith"]
    conf = {s["name"]: s["confidence"] for s in rob["skills"]}
    assert conf["Python"] > 0.9          # multi-source corroboration
    assert conf["React"] < 0.5           # inferred from notes only -> honestly low


def test_international_phone_uses_country(sample_inputs):
    priya = _by_name(run_pipeline(sample_inputs))["Priya Sharma"]
    assert priya["phones"] == ["+919876543210"]
    assert priya["location"]["country"] == "IN"


def test_deterministic_regardless_of_input_order(sample_inputs):
    a = run_pipeline(sample_inputs)
    b = run_pipeline(list(reversed(sample_inputs)))
    assert json.dumps(a) == json.dumps(b)


def test_custom_config_projection_and_on_missing_null(sample_inputs):
    cfg = {
        "fields": [
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
            {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
            {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"},
        ],
        "include_provenance": False, "on_missing": "null",
    }
    res = _by_name(run_pipeline(sample_inputs, cfg))
    assert res["Robert Smith"]["primary_email"] == "robert@acme.com"
    assert "provenance" not in res["Robert Smith"]           # toggled off
    assert res["Bob Smith"]["phone"] is None                 # missing -> null


def test_on_missing_error_raises(sample_inputs):
    cfg = {"fields": [{"path": "x", "from": "links.nonexistent", "type": "string"}],
           "on_missing": "error"}
    with pytest.raises(MissingFieldError):
        run_pipeline(sample_inputs, cfg)


def test_required_field_cannot_be_null(sample_inputs):
    cfg = {"fields": [{"path": "x", "from": "links.nonexistent",
                       "type": "string", "required": True}],
           "on_missing": "null"}
    with pytest.raises(jsonschema.ValidationError):
        run_pipeline(sample_inputs, cfg)


def test_on_missing_omit_drops_field(sample_inputs):
    cfg = {"fields": [{"path": "full_name", "type": "string"},
                      {"path": "gh", "from": "links.github", "type": "string"}],
           "on_missing": "omit", "include_provenance": False, "include_confidence": False}
    res = _by_name(run_pipeline(sample_inputs, cfg))
    assert "gh" not in res["Bob Smith"]                  # missing -> omitted entirely
    assert res["Robert Smith"]["gh"].endswith("robsmith")  # present -> kept


def test_experience_and_education_merge(sample_inputs):
    rob = _by_name(run_pipeline(sample_inputs))["Robert Smith"]
    companies = [e["company"] for e in rob["experience"]]
    assert companies.count("Acme Corp") == 1   # CSV + ATS current role collapse to one
    assert "Globex" in companies               # distinct prior role kept separate
    assert rob["education"][0]["institution"] == "UT Austin"
