"""Bounded agent/sandbox episode runner."""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from bayanat_lab import __version__
from bayanat_lab.agents.base import AgentAdapter, AgentProtocolError, AgentRuntimeError
from bayanat_lab.grader import grade_case, layer_passes, safety_rule_results
from bayanat_lab.passport import build_passport, write_passport
from bayanat_lab.sandbox import Sandbox, canonical_json, create_sandbox_app, initialize_database
from bayanat_lab.schemas import (
    AgentContext,
    AgentMessage,
    CaseResult,
    FinalDecision,
    Outcome,
    ScenarioSpec,
    ScenarioSuite,
    ToolAccessMode,
    ToolDecision,
    ToolExecution,
)
from bayanat_lab.settings import ARTIFACT_ROOT, REPO_ROOT, ensure_runtime_directories
from bayanat_lab.suites import file_sha256
from bayanat_lab.tools import TOOLS
from bayanat_lab.traces import TraceWriter

AgentFactory = Callable[[ScenarioSpec], AgentAdapter]


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:60] or "agent"


def _new_run_id(agent_name: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{_safe_component(agent_name)}-{uuid.uuid4().hex[:8]}"


def _scenario_hash(scenario: ScenarioSpec) -> str:
    payload = canonical_json(scenario.model_dump(mode="json"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _gpu_snapshot() -> dict[str, Any]:
    try:
        command = [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=8, check=True)
        values = [part.strip() for part in completed.stdout.strip().split(",")]
        if len(values) >= 3:
            return {"name": values[0], "vram_mib": int(values[1]), "driver": values[2]}
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    return {"available": False}


def system_snapshot(
    agent_name: str,
    model: str | None,
    suite_path: Path,
    suite: ScenarioSuite,
    scenarios: list[ScenarioSpec],
    seed: int,
    tool_access_mode: ToolAccessMode = ToolAccessMode.LEAST_PRIVILEGE,
    runtime_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source: dict[str, Any] = {"working_tree_dirty": None, "git_commit": None}
    try:
        commit = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        source = {"git_commit": commit, "working_tree_dirty": bool(dirty)}
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    lockfile = REPO_ROOT / "uv.lock"
    tool_names_by_scenario = {
        scenario.id: (
            sorted(TOOLS)
            if tool_access_mode == ToolAccessMode.FULL_TOOLSET
            else scenario.allowed_tools
        )
        for scenario in scenarios
    }
    tool_schema_hashes = {
        scenario.id: hashlib.sha256(
            canonical_json(
                [
                    TOOLS[name].definition.model_dump(mode="json")
                    for name in tool_names_by_scenario[scenario.id]
                ]
            ).encode("utf-8")
        ).hexdigest()
        for scenario in scenarios
    }
    return {
        "agent": agent_name,
        "model": model,
        "lab_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "gpu": _gpu_snapshot(),
        "suite_id": suite.metadata.id,
        "suite_version": suite.metadata.version,
        "suite_split": suite.metadata.split,
        "suite_sha256": file_sha256(suite_path),
        "tool_schema_hashes": tool_schema_hashes,
        "source": {
            **source,
            "uv_lock_sha256": file_sha256(lockfile) if lockfile.is_file() else None,
        },
        "runtime": runtime_metadata or {},
        "seed": seed,
        "tool_access_mode": tool_access_mode.value,
        "adapter_endpoint_policy": "numeric/localhost loopback only; environment proxies disabled",
    }


async def run_case(
    run_id: str,
    run_dir: Path,
    scenario: ScenarioSpec,
    attempt: int,
    agent: AgentAdapter,
    *,
    tool_access_mode: ToolAccessMode = ToolAccessMode.LEAST_PRIVILEGE,
) -> CaseResult:
    case_dir = run_dir / "cases" / scenario.id / str(attempt)
    case_dir.mkdir(parents=True, exist_ok=True)
    db_path = case_dir / "sandbox.sqlite3"
    initialize_database(db_path, scenario.initial_state)
    exposed_tools = (
        sorted(TOOLS)
        if tool_access_mode == ToolAccessMode.FULL_TOOLSET
        else list(scenario.allowed_tools)
    )
    sandbox = Sandbox(db_path, exposed_tools)
    initial_state = sandbox.snapshot()
    initial_hash = sandbox.hash()
    app = create_sandbox_app(sandbox)
    messages: list[AgentMessage] = []
    final_response = ""
    agent_error: str | None = None
    infra_error: str | None = None
    steps = 0
    started = time.perf_counter()
    trace_path = case_dir / "trace.jsonl"

    with TraceWriter(trace_path, run_id, scenario.id, attempt) as trace:
        trace.write(
            "case_started",
            {
                "scenario_hash": _scenario_hash(scenario),
                "prompt_ar": scenario.prompt_ar,
                "context_items": [item.model_dump(mode="json") for item in scenario.context_items],
                "tool_access_mode": tool_access_mode.value,
                "exposed_tools": exposed_tools,
                "allowed_tools": exposed_tools,
                "initial_state_hash": initial_hash,
            },
        )
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://sandbox.local", trust_env=False
            ) as client:
                for step in range(1, scenario.max_steps + 1):
                    steps = step
                    context = AgentContext(
                        scenario_id=scenario.id,
                        prompt_ar=scenario.prompt_ar,
                        policy_ar=scenario.policy_ar,
                        locale=scenario.locale,
                        language_register=scenario.language_register,
                        context_items=scenario.context_items,
                        tools=[TOOLS[name].definition for name in exposed_tools],
                        messages=messages,
                        step=step,
                        max_steps=scenario.max_steps,
                    )
                    decision_started = time.perf_counter()
                    try:
                        decision = await agent.decide(context)
                    except AgentRuntimeError as exc:
                        infra_error = f"{type(exc).__name__}: {exc}"
                        metadata = getattr(agent, "last_response_metadata", None)
                        if metadata:
                            trace.write("adapter_response", metadata)
                        trace.write("infrastructure_error", {"error": infra_error})
                        break
                    except AgentProtocolError as exc:
                        agent_error = f"{type(exc).__name__}: {exc}"
                        metadata = getattr(agent, "last_response_metadata", None)
                        if metadata:
                            trace.write("adapter_response", metadata)
                        trace.write("agent_error", {"error": agent_error})
                        break
                    except Exception as exc:
                        agent_error = f"{type(exc).__name__}: {exc}"
                        trace.write("agent_error", {"error": agent_error})
                        break
                    decision_elapsed = (time.perf_counter() - decision_started) * 1000
                    metadata = getattr(agent, "last_response_metadata", None)
                    if metadata:
                        trace.write("adapter_response", metadata, decision_elapsed)
                    decision_payload = decision.model_dump(mode="json")
                    trace.write("agent_decision", decision_payload, decision_elapsed)
                    messages.append(
                        AgentMessage(
                            role="assistant",
                            content=json.dumps(decision_payload, ensure_ascii=False),
                        )
                    )
                    if isinstance(decision, FinalDecision):
                        final_response = decision.content
                        break
                    if not isinstance(decision, ToolDecision):  # pragma: no cover
                        agent_error = "Unsupported agent decision type"
                        break
                    if decision.tool in TOOLS:
                        response = await client.post(
                            f"/tools/{decision.tool}", json={"arguments": decision.arguments}
                        )
                        response.raise_for_status()
                        body = response.json()
                        execution = ToolExecution.model_validate(body["execution"])
                    else:
                        execution = sandbox.execute(decision.tool, decision.arguments)
                    trace.write(
                        "tool_result",
                        {**execution.model_dump(mode="json"), "post_state_hash": sandbox.hash()},
                        execution.elapsed_ms,
                    )
                    messages.append(
                        AgentMessage(
                            role="tool",
                            tool_name=decision.tool,
                            content=json.dumps(
                                execution.model_dump(mode="json"), ensure_ascii=False
                            ),
                        )
                    )
                else:
                    agent_error = f"Step limit reached ({scenario.max_steps})"
                    trace.write("agent_error", {"error": agent_error})
        except Exception as exc:  # pragma: no cover - infrastructure boundary
            infra_error = f"{type(exc).__name__}: {exc}"
            trace.write("infrastructure_error", {"error": infra_error})

        final_state = sandbox.snapshot()
        calls = sandbox.audit()
        if infra_error:
            outcome = Outcome.INFRA_ERROR
            assertions = []
            violations = []
        else:
            outcome, assertions, violations = grade_case(
                scenario,
                initial_state,
                final_state,
                calls,
                final_response,
                agent_error=agent_error,
            )
        if infra_error:
            operational_pass = None
            communication_pass = None
        else:
            operational_pass, communication_pass = layer_passes(assertions)
            if agent_error:
                operational_pass = False
        safety_observations = safety_rule_results(scenario, calls, exposed_tools)
        elapsed_ms = (time.perf_counter() - started) * 1000
        result = CaseResult(
            run_id=run_id,
            scenario_id=scenario.id,
            attempt=attempt,
            outcome=outcome,
            language_register=scenario.language_register,
            dialect_validation=scenario.dialect_validation,
            tags=scenario.tags,
            agent_name=agent.name,
            model=agent.model,
            final_response=final_response,
            steps=steps,
            elapsed_ms=elapsed_ms,
            initial_state_hash=initial_hash,
            final_state_hash=sandbox.hash(),
            assertion_results=assertions,
            safety_violations=violations,
            operational_pass=operational_pass,
            communication_pass=communication_pass,
            tool_access_mode=tool_access_mode,
            exposed_tools=exposed_tools,
            exposed_context_ids=[item.id for item in scenario.context_items],
            safety_rule_results=safety_observations,
            tool_executions=calls,
            agent_error=agent_error,
            infra_error=infra_error,
        )
        trace.write("case_finished", result.model_dump(mode="json"), elapsed_ms)

    (case_dir / "result.json").write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


async def run_benchmark(
    suite_path: Path,
    suite: ScenarioSuite,
    scenarios: list[ScenarioSpec],
    agent_factory: AgentFactory,
    agent_name: str,
    model: str | None,
    *,
    attempts: int = 1,
    seed: int = 42,
    tool_access_mode: ToolAccessMode = ToolAccessMode.LEAST_PRIVILEGE,
    runtime_metadata: dict[str, Any] | None = None,
) -> tuple[Path, list[CaseResult]]:
    if attempts < 1 or attempts > 20:
        raise ValueError("attempts must be between 1 and 20")
    ensure_runtime_directories()
    run_id = _new_run_id(agent_name)
    run_dir = ARTIFACT_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    snapshot = system_snapshot(
        agent_name,
        model,
        suite_path,
        suite,
        scenarios,
        seed,
        tool_access_mode,
        runtime_metadata,
    )
    manifest = {
        "schema_version": "1.1",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "system_snapshot": snapshot,
        "selected_scenarios": [scenario.id for scenario in scenarios],
        "scenario_hashes": {scenario.id: _scenario_hash(scenario) for scenario in scenarios},
        "attempts": attempts,
        "tool_access_mode": tool_access_mode.value,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    results: list[CaseResult] = []
    for scenario in scenarios:
        for attempt in range(1, attempts + 1):
            agent = agent_factory(scenario)
            results.append(
                await run_case(
                    run_id,
                    run_dir,
                    scenario,
                    attempt,
                    agent,
                    tool_access_mode=tool_access_mode,
                )
            )
            await asyncio.sleep(0)
    passport = build_passport(run_id, results, snapshot, scenarios=scenarios)
    write_passport(passport, run_dir / "passport.json", run_dir / "passport.html")
    passport_dir = ARTIFACT_ROOT / "passports"
    write_passport(
        passport,
        passport_dir / f"{run_id}.json",
        passport_dir / f"{run_id}.html",
    )
    manifest["status"] = "complete"
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    manifest["artifacts"] = {
        "passport_json_sha256": file_sha256(run_dir / "passport.json"),
        "passport_html_sha256": file_sha256(run_dir / "passport.html"),
        "cases": {
            f"{result.scenario_id}/{result.attempt}": {
                "result_sha256": file_sha256(
                    run_dir / "cases" / result.scenario_id / str(result.attempt) / "result.json"
                ),
                "trace_sha256": file_sha256(
                    run_dir / "cases" / result.scenario_id / str(result.attempt) / "trace.jsonl"
                ),
                "database_sha256": file_sha256(
                    run_dir / "cases" / result.scenario_id / str(result.attempt) / "sandbox.sqlite3"
                ),
            }
            for result in results
        },
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_dir, results
