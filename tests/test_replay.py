import asyncio
import json

import pytest

from bayanat_lab.agents.rule import RuleAgent
from bayanat_lab.replay import ReplayMismatchError, replay_trace
from bayanat_lab.runner import run_case


def test_replay_reproduces_tool_calls_and_final_state(tmp_path, suite):
    scenario = suite.scenarios[2]
    run_dir = tmp_path / "run"
    result = asyncio.run(run_case("REPLAY-RUN", run_dir, scenario, 1, RuleAgent()))
    trace_path = run_dir / "cases" / scenario.id / "1" / "trace.jsonl"

    receipt = replay_trace(trace_path, suite)

    assert receipt["case_id"] == scenario.id
    assert receipt["tool_calls"] == len(result.tool_executions)
    assert receipt["final_state_hash"] == result.final_state_hash


def test_replay_rejects_different_scenario_source(tmp_path, suite):
    scenario = suite.scenarios[0]
    run_dir = tmp_path / "run"
    asyncio.run(run_case("REPLAY-RUN", run_dir, scenario, 1, RuleAgent()))
    trace_path = run_dir / "cases" / scenario.id / "1" / "trace.jsonl"
    changed_suite = suite.model_copy(deep=True)
    changed_suite.scenarios[0].prompt_ar += " تغيير"

    with pytest.raises(ReplayMismatchError, match="Scenario source"):
        replay_trace(trace_path, changed_suite)


def test_replay_rejects_tampered_tool_receipt(tmp_path, suite):
    scenario = suite.scenarios[2]
    run_dir = tmp_path / "run"
    asyncio.run(run_case("REPLAY-RUN", run_dir, scenario, 1, RuleAgent()))
    trace_path = run_dir / "cases" / scenario.id / "1" / "trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    tool_event = next(event for event in events if event["event_type"] == "tool_result")
    tool_event["payload"]["result"] = {"forged": True}
    trace_path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="Invalid event hash"):
        replay_trace(trace_path, suite)
