from candidate_transformer.normalize import (
    canonical_skill, normalize_country, normalize_date, normalize_email, normalize_phone)


def test_phone_e164_local_and_intl_collapse_to_same():
    assert normalize_phone("(555) 123-4567") == "+15551234567"
    assert normalize_phone("+1 555 123 4567") == "+15551234567"   # normalize-before-merge


def test_phone_uses_region_hint_for_local_numbers():
    assert normalize_phone("98765 43210", region="IN") == "+919876543210"


def test_phone_rejects_garbage():
    assert normalize_phone("not-a-number") is None
    assert normalize_phone("12") is None


def test_country_to_iso_alpha2():
    assert normalize_country("United States") == "US"
    assert normalize_country("USA") == "US"
    assert normalize_country("India") == "IN"
    assert normalize_country("Atlantis") is None


def test_dates():
    assert normalize_date("2020-6") == "2020-06"
    assert normalize_date("Jan 2020") == "2020-01"
    assert normalize_date("06/2019") == "2019-06"
    assert normalize_date("2018") == "2018"          # year only: no invented month
    assert normalize_date("Present") is None


def test_skill_canonicalization():
    assert canonical_skill("js") == "JavaScript"
    assert canonical_skill("K8S") == "Kubernetes"
    assert canonical_skill("SomeNewLib") == "SomeNewLib"   # unknown kept


def test_email():
    assert normalize_email("Robert@Acme.com") == "robert@acme.com"
    assert normalize_email("nope") is None
