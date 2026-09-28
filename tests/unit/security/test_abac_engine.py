"""Unit tests for ABACEngine per §19.3."""

from app.security.authz.abac_engine import ABACEngine


def test_abac_evaluates_empty_conditions_as_true() -> None:
    engine = ABACEngine()
    assert engine.evaluate({"role": "admin"}, {"type": "report"}, "read", {}) is True


def test_abac_evaluates_equals_and_not_equals() -> None:
    engine = ABACEngine()
    subject = {"department": "research"}
    resource = {"classification": "public"}

    # equals True
    cond_eq = {"department": {"operator": "equals", "value": "research"}}
    assert engine.evaluate(subject, resource, "read", cond_eq) is True

    # not_equals True
    cond_neq = {"classification": {"operator": "not_equals", "value": "top_secret"}}
    assert engine.evaluate(subject, resource, "read", cond_neq) is True


def test_abac_evaluates_in_and_not_in() -> None:
    engine = ABACEngine()
    subject = {"clearance": "L2"}
    resource = {"allowed_levels": ["L1", "L2", "L3"]}

    cond_in = {"clearance": {"operator": "in", "value": ["L2", "L3"]}}
    assert engine.evaluate(subject, resource, "read", cond_in) is True

    cond_not_in = {"clearance": {"operator": "not_in", "value": ["L0", "L1"]}}
    assert engine.evaluate(subject, resource, "read", cond_not_in) is True


def test_abac_evaluates_comparisons() -> None:
    engine = ABACEngine()
    subject = {"level": 5}
    resource = {"min_level": 3}

    cond_gt = {"level": {"operator": "greater_than", "value": 2}}
    assert engine.evaluate(subject, resource, "read", cond_gt) is True

    cond_lt = {"level": {"operator": "less_than", "value": 10}}
    assert engine.evaluate(subject, resource, "read", cond_lt) is True


def test_abac_evaluates_nested_fields() -> None:
    engine = ABACEngine()
    subject = {"user": {"org": {"id": "org_42"}}}
    resource = {}

    cond = {"user.org.id": {"operator": "equals", "value": "org_42"}}
    assert engine.evaluate(subject, resource, "read", cond) is True

    cond_missing = {"user.missing.key": {"operator": "equals", "value": "x"}}
    assert engine.evaluate(subject, resource, "read", cond_missing) is False
