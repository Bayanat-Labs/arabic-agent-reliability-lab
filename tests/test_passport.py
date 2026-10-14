import asyncio

from bayanat_lab.agents.rule import RuleAgent
from bayanat_lab.passport import build_passport, render_passport_html, wilson_interval
from bayanat_lab.runner import run_case
from bayanat_lab.schemas import Passport


def test_wilson_interval_known_boundaries():
    empty = wilson_interval(0, 0)
    assert empty == {"successes": 0, "total": 0, "rate": 0.0, "low": 0.0, "high": 0.0}
    full = wilson_interval(20, 20)
    assert full["rate"] == 1.0
    assert 0.83 < full["low"] < 0.85
    assert full["high"] == 1.0


def test_passport_html_is_english_first_with_plain_failure_explanations():
    passport = Passport(
        run_id="RUN-ENGLISH",
        generated_at="2026-08-05T00:00:00Z",
        system_snapshot={"model": "local-model", "runtime": {"model_digest": "abc123"}},
        counts={
            "pass": 2,
            "task_fail": 1,
            "unsafe_fail": 0,
            "agent_error": 0,
            "infra_error": 0,
            "invalid_case": 0,
        },
        metrics={
            "task_success": {"rate": 0.5, "successes": 1, "total": 2, "low": 0.1, "high": 0.9},
            "forbidden_action_attempt": {
                "rate": 0.0,
                "successes": 0,
                "total": 2,
                "low": 0.0,
                "high": 0.66,
            },
            "forbidden_attempt_counts": {"blocked": 0, "executed": 0},
            "stability": {"identical_outcome": {"rate": 1.0, "successes": 2, "total": 2}},
            "attempt_denominator": 3,
            "mean_steps": 2.0,
        },
        slices={},
        warnings=["تنبيه عربي"],
        cases=[
            {
                "scenario_id": "BARL-COM-003",
                "attempt": 1,
                "outcome": "task_fail",
                "register": "msa",
                "dialect_validation": "not_applicable_msa",
                "failed_assertions_en": [
                    "[MAJOR] Required tool action was not completed: update_shipping_address."
                ],
            }
        ],
    )

    rendered = render_passport_html(passport)

    assert '<html lang="en" dir="ltr">' in rendered
    assert "Arabic Agent Reliability Passport" in rendered
    assert "Task failure" in rendered
    assert "Required tool action was not completed" in rendered
    assert "Unvalidated — native review required" not in rendered


def test_passport_separates_layers_opportunities_and_repeat_agreement(tmp_path, suite):
    scenario = suite.scenarios[0]

    async def run_attempts():
        first = await run_case("RUN-LAYERS", tmp_path / "run", scenario, 1, RuleAgent())
        second = await run_case("RUN-LAYERS", tmp_path / "run", scenario, 2, RuleAgent())
        return first, second

    first, second = asyncio.run(run_attempts())
    second = second.model_copy(update={"final_response": f"{second.final_response} !!!"})
    passport = build_passport(
        "RUN-LAYERS",
        [first, second],
        {"agent": "test-agent", "tool_access_mode": "least_privilege"},
        scenarios=[scenario],
    )

    assert passport.metrics["operational_completion"]["successes"] == 1
    assert passport.metrics["communication_quality"]["successes"] == 1
    safety = passport.metrics["safety_evaluation"]
    assert safety["family_denominators"]["at_least_one_rule_tool_available"] == 0
    assert safety["family_denominators"]["rules_only_unavailable_by_construction"] == 1
    assert safety["rule_opportunities"]["unavailable_by_construction"] == 2
    stability = passport.metrics["stability"]
    assert stability["repeated_family_denominator"] == 1
    assert stability["identical_tool_trajectory"]["successes"] == 1
    assert stability["identical_normalized_final_response"]["successes"] == 1
