import json

import pytest

from bayanat_lab.suites import SuiteValidationError, load_suite


def test_v02_suite_has_expected_preview_shape_and_paired_security_probe(suite):
    assert len(suite.scenarios) == 21
    assert sum(item.language_register == "msa" for item in suite.scenarios) == 10
    colloquial = [
        item for item in suite.scenarios if item.language_register == "saudi_oriented_colloquial"
    ]
    assert len(colloquial) == 11
    assert all(
        item.dialect_validation == "unvalidated_native_review_required" for item in colloquial
    )
    assert all(item.origin == "synthetic" for item in suite.scenarios)
    probe_cases = [item for item in suite.scenarios if item.security_probe]
    assert {item.security_probe.condition for item in probe_cases} == {
        "adversarial_injection",
        "benign_control",
    }
    assert all(item.context_items for item in probe_cases)
    assert all(item.context_items[0].trust == "untrusted" for item in probe_cases)


def test_suite_rejects_unknown_tool(tmp_path, suite_path):
    raw = json.loads(suite_path.read_text(encoding="utf-8"))
    raw["scenarios"][0]["allowed_tools"].append("run_arbitrary_shell")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SuiteValidationError, match="unknown allowed tools"):
        load_suite(bad)


def test_agent_policy_is_inherited_without_exposing_gold(suite):
    scenario = suite.scenarios[0]
    assert scenario.policy_ar
    assert scenario.assertions
    assert "تأكيد" in " ".join(scenario.policy_ar)
