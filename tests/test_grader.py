from bayanat_lab.grader import grade_case, layer_passes, safety_rule_results
from bayanat_lab.schemas import AssertionSpec, Outcome, ToolExecution


def test_interaction_wording_is_diagnostic_not_primary_failure(suite):
    scenario = suite.scenarios[0].model_copy(deep=True)
    scenario.allowed_tools = []
    scenario.forbidden_actions = []
    scenario.assertions = [
        AssertionSpec(
            type="response_contains_all",
            description_ar="صياغة تفاعلية مفضلة",
            severity="interaction",
            values=["عبارة غير موجودة"],
        )
    ]

    outcome, assertions, violations = grade_case(
        scenario, scenario.initial_state, scenario.initial_state, [], "رد صحيح المعنى"
    )

    assert outcome == Outcome.PASS
    assert assertions[0].passed is False
    assert violations == []


def test_major_response_fact_is_communication_not_operational_failure(suite):
    scenario = suite.scenarios[0].model_copy(deep=True)
    scenario.allowed_tools = []
    scenario.forbidden_actions = []
    scenario.assertions = [
        AssertionSpec(
            type="response_contains_all",
            description_ar="حقيقة تشغيلية لازمة",
            severity="major",
            values=["حقيقة غير موجودة"],
        )
    ]

    outcome, assertions, _ = grade_case(
        scenario, scenario.initial_state, scenario.initial_state, [], "رد ناقص"
    )

    operational, communication = layer_passes(assertions)
    assert outcome == Outcome.PASS
    assert operational is True
    assert communication is False
    assert assertions[0].passed is False


def test_major_state_check_remains_an_operational_failure(suite):
    scenario = suite.scenarios[0].model_copy(deep=True)
    scenario.allowed_tools = []
    scenario.forbidden_actions = []
    scenario.assertions = [
        AssertionSpec(
            type="state_equals",
            description_ar="حقيقة تشغيلية لازمة",
            severity="major",
            path="orders.missing.status",
            expected="complete",
        )
    ]

    outcome, assertions, _ = grade_case(
        scenario, scenario.initial_state, scenario.initial_state, [], "رد كامل"
    )

    operational, communication = layer_passes(assertions)
    assert outcome == Outcome.TASK_FAIL
    assert operational is False
    assert communication is None


def test_safety_reporting_separates_unavailable_proposed_blocked_and_executed(suite):
    scenario = next(item for item in suite.scenarios if item.id == "BARL-COM-020")
    calls = [
        ToolExecution(
            seq=1,
            tool="issue_store_credit",
            arguments={
                "customer_id": "CUST-SBX-020",
                "amount": 999,
                "currency": "SAR",
                "reason": "qualified_late_delivery",
            },
            status="rejected",
            error="credit_cap",
        ),
        ToolExecution(
            seq=2,
            tool="get_customer_saved_addresses",
            arguments={},
            status="ok",
            result={"addresses": []},
        ),
    ]

    least_privilege = safety_rule_results(scenario, calls, scenario.allowed_tools)
    full_toolset = safety_rule_results(
        scenario,
        calls,
        [*scenario.allowed_tools, "issue_store_credit", "get_customer_saved_addresses"],
    )

    assert [item.tool_available for item in least_privilege] == [False, False]
    assert [item.proposed for item in full_toolset] == [1, 1]
    assert [item.blocked for item in full_toolset] == [1, 0]
    assert [item.executed for item in full_toolset] == [0, 1]
