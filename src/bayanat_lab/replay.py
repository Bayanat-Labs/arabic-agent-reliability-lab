"""Deterministically replay recorded tool calls against a fresh sandbox."""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from bayanat_lab.sandbox import Sandbox, canonical_json, initialize_database
from bayanat_lab.schemas import ScenarioSpec, ScenarioSuite
from bayanat_lab.traces import read_trace


class ReplayMismatchError(ValueError):
    """Raised when a trace cannot be reproduced from its scenario fixture."""


def scenario_hash(scenario: ScenarioSpec) -> str:
    payload = canonical_json(scenario.model_dump(mode="json"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scenario_for_trace(suite: ScenarioSuite, case_id: str) -> ScenarioSpec:
    matches = [scenario for scenario in suite.scenarios if scenario.id == case_id]
    if len(matches) != 1:
        raise ReplayMismatchError(f"Scenario {case_id!r} is not uniquely present in the suite")
    return matches[0]


def replay_trace(path: Path, suite: ScenarioSuite) -> dict[str, Any]:
    """Verify and replay a complete trace, returning a compact receipt."""

    events = read_trace(path, verify=True)
    case_id = str(events[0]["case_id"])
    scenario = _scenario_for_trace(suite, case_id)
    started = events[0]["payload"]
    expected_scenario_hash = scenario_hash(scenario)
    if started.get("scenario_hash") != expected_scenario_hash:
        raise ReplayMismatchError("Scenario source does not match the hash committed by the trace")

    with TemporaryDirectory(prefix="barl-replay-") as temp_dir:
        db_path = Path(temp_dir) / "sandbox.sqlite3"
        initialize_database(db_path, scenario.initial_state)
        recorded_tools = started.get("exposed_tools", started.get("allowed_tools"))
        replay_tools = recorded_tools if isinstance(recorded_tools, list) else scenario.allowed_tools
        sandbox = Sandbox(db_path, replay_tools)
        if sandbox.hash() != started.get("initial_state_hash"):
            raise ReplayMismatchError("Fresh sandbox does not match the committed initial state")

        replayed_calls = 0
        for event in events:
            if event.get("event_type") != "tool_result":
                continue
            recorded = event["payload"]
            actual = sandbox.execute(recorded["tool"], recorded.get("arguments", {}))
            comparable_actual = {
                "seq": actual.seq,
                "tool": actual.tool,
                "arguments": actual.arguments,
                "status": actual.status,
                "result": actual.result,
                "error": actual.error,
                "mutated_state": actual.mutated_state,
                "post_state_hash": sandbox.hash(),
            }
            comparable_recorded = {
                key: recorded.get(key)
                for key in (
                    "seq",
                    "tool",
                    "arguments",
                    "status",
                    "result",
                    "error",
                    "mutated_state",
                    "post_state_hash",
                )
            }
            if comparable_actual != comparable_recorded:
                raise ReplayMismatchError(
                    f"Tool call {replayed_calls + 1} diverged: "
                    f"expected {canonical_json(comparable_recorded)}, "
                    f"observed {canonical_json(comparable_actual)}"
                )
            replayed_calls += 1

        finished = events[-1]["payload"]
        final_hash = sandbox.hash()
        if final_hash != finished.get("final_state_hash"):
            raise ReplayMismatchError(
                "Replayed final state does not match the trace terminal event"
            )
        if replayed_calls != len(finished.get("tool_executions", [])):
            raise ReplayMismatchError("Replayed tool count does not match the terminal result")

    return {
        "case_id": case_id,
        "attempt": events[0]["attempt"],
        "events": len(events),
        "tool_calls": replayed_calls,
        "tool_access_mode": started.get("tool_access_mode", "least_privilege"),
        "scenario_hash": expected_scenario_hash,
        "final_state_hash": final_hash,
        "trace_final_hash": events[-1]["event_hash"],
    }
