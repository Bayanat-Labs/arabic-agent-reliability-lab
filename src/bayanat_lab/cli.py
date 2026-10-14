"""Command-line interface for local benchmark operations."""

from __future__ import annotations

import asyncio
import json
import platform
import sqlite3
import sys
from pathlib import Path
from typing import Annotated

import httpx
import typer
import uvicorn

from bayanat_lab.agents.base import AgentRuntimeError
from bayanat_lab.agents.ollama import OllamaAgent
from bayanat_lab.agents.rule import RuleAgent
from bayanat_lab.dashboard import create_dashboard_app
from bayanat_lab.replay import ReplayMismatchError, replay_trace
from bayanat_lab.runner import run_benchmark
from bayanat_lab.schemas import Outcome, ToolAccessMode
from bayanat_lab.settings import (
    ARTIFACT_ROOT,
    DEFAULT_DASHBOARD_HOST,
    DEFAULT_DASHBOARD_PORT,
    DEFAULT_OLLAMA_URL,
    DEFAULT_SUITE,
    require_loopback_host,
    require_loopback_url,
)
from bayanat_lab.suites import SuiteValidationError, load_suite, select_scenarios
from bayanat_lab.traces import TraceIntegrityError, read_trace

app = typer.Typer(
    name="barl",
    help="Bayanat Arabic Agent Reliability Lab — local Arabic agent crash tests.",
    no_args_is_help=True,
)


def _suite(path: Path):
    try:
        return load_suite(path)
    except SuiteValidationError as exc:
        typer.echo(f"Suite validation failed:\n{exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def doctor(
    suite: Annotated[Path, typer.Option(help="Scenario suite JSON path.")] = DEFAULT_SUITE,
    ollama_url: Annotated[str, typer.Option(help="Loopback Ollama URL.")] = DEFAULT_OLLAMA_URL,
) -> None:
    """Inspect prerequisites without installing software or pulling a model."""

    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python", sys.version_info[:2] == (3, 12), platform.python_version()))
    checks.append(("SQLite", sqlite3.sqlite_version_info >= (3, 35), sqlite3.sqlite_version))
    try:
        loaded = load_suite(suite)
        checks.append(("Suite", True, f"{loaded.metadata.id} · {len(loaded.scenarios)} scenarios"))
    except SuiteValidationError as exc:
        checks.append(("Suite", False, str(exc).splitlines()[0]))
    try:
        local_url = require_loopback_url(ollama_url)
        with httpx.Client(timeout=2.0, trust_env=False) as client:
            response = client.get(f"{local_url}/api/version")
            response.raise_for_status()
            checks.append(("Ollama", True, str(response.json().get("version", "reachable"))))
    except Exception as exc:
        checks.append(("Ollama", False, f"not running ({type(exc).__name__})"))
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    checks.append(("Artifacts", ARTIFACT_ROOT.is_dir(), str(ARTIFACT_ROOT)))
    for name, ok, detail in checks:
        typer.echo(f"[{'OK' if ok else 'WARN'}] {name}: {detail}")
    if not all(ok for name, ok, _ in checks if name != "Ollama"):
        raise typer.Exit(4)


@app.command("validate")
def validate_suite(
    suite: Annotated[Path, typer.Option(help="Scenario suite JSON path.")] = DEFAULT_SUITE,
) -> None:
    """Validate schemas, tool references, provenance labels, and IDs."""

    loaded = _suite(suite)
    counts: dict[str, int] = {}
    for scenario in loaded.scenarios:
        counts[scenario.language_register] = counts.get(scenario.language_register, 0) + 1
    typer.echo(
        f"Valid: {loaded.metadata.id} {loaded.metadata.version} · "
        f"{len(loaded.scenarios)} scenarios · {json.dumps(counts, ensure_ascii=False)}"
    )


@app.command("list-scenarios")
def list_scenarios(
    suite: Annotated[Path, typer.Option(help="Scenario suite JSON path.")] = DEFAULT_SUITE,
) -> None:
    """List the open v0 cases and validation status."""

    loaded = _suite(suite)
    for scenario in loaded.scenarios:
        typer.echo(
            f"{scenario.id}\t{scenario.language_register}\t"
            f"{scenario.dialect_validation}\t{scenario.title_en}"
        )


@app.command()
def benchmark(
    agent: Annotated[str, typer.Option(help="Agent adapter: rule or ollama.")] = "rule",
    model: Annotated[str | None, typer.Option(help="Pre-pulled Ollama model tag.")] = None,
    suite: Annotated[Path, typer.Option(help="Scenario suite JSON path.")] = DEFAULT_SUITE,
    scenario: Annotated[
        list[str] | None, typer.Option("--scenario", help="Scenario ID; repeatable.")
    ] = None,
    register: Annotated[str | None, typer.Option(help="Optional register filter.")] = None,
    limit: Annotated[int | None, typer.Option(min=1, max=20)] = None,
    attempts: Annotated[int, typer.Option(min=1, max=20)] = 1,
    seed: Annotated[int, typer.Option()] = 42,
    tool_access: Annotated[
        ToolAccessMode,
        typer.Option(
            help=(
                "Tool evaluability mode: least_privilege exposes only task tools; "
                "full_toolset exposes the complete synthetic registry."
            )
        ),
    ] = ToolAccessMode.LEAST_PRIVILEGE,
    ollama_url: Annotated[str, typer.Option(help="Loopback Ollama URL.")] = DEFAULT_OLLAMA_URL,
) -> None:
    """Run selected scenarios and generate a Reliability Passport."""

    loaded = _suite(suite)
    try:
        selected = select_scenarios(loaded, scenario, register, limit)
    except SuiteValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    if agent == "rule":
        agent_name = RuleAgent.name
        model_name = None
        runtime_metadata = {
            "baseline_role": "harness/open-case regression control; not model evidence"
        }

        def factory(_: object) -> RuleAgent:
            return RuleAgent()

    elif agent == "ollama":
        if not model:
            typer.echo("--model is required for the Ollama adapter.", err=True)
            raise typer.Exit(2)
        try:
            local_url = require_loopback_url(ollama_url)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from exc
        agent_name = OllamaAgent.name
        model_name = model
        probe = OllamaAgent(model=model, base_url=local_url, seed=seed)
        try:
            runtime_metadata = asyncio.run(probe.inspect())
        except AgentRuntimeError as exc:
            typer.echo(f"Local model preflight failed: {exc}", err=True)
            raise typer.Exit(3) from exc

        def factory(_: object) -> OllamaAgent:
            return OllamaAgent(model=model, base_url=local_url, seed=seed)

    else:
        typer.echo("--agent must be 'rule' or 'ollama'.", err=True)
        raise typer.Exit(2)
    typer.echo(
        f"Running {len(selected)} scenario(s) × {attempts} attempt(s) with {agent_name} "
        f"[{tool_access.value}]..."
    )
    run_dir, results = asyncio.run(
        run_benchmark(
            suite,
            loaded,
            selected,
            factory,
            agent_name,
            model_name,
            attempts=attempts,
            seed=seed,
            tool_access_mode=tool_access,
            runtime_metadata=runtime_metadata,
        )
    )
    counts = {
        outcome.value: sum(result.outcome == outcome for result in results) for outcome in Outcome
    }
    typer.echo(f"Completed: {json.dumps(counts, ensure_ascii=False)}")
    typer.echo(f"Passport: {run_dir / 'passport.html'}")
    if counts[Outcome.INFRA_ERROR.value]:
        raise typer.Exit(4)


@app.command("verify-trace")
def verify_trace(path: Path) -> None:
    """Verify JSONL structure and its complete SHA-256 hash chain."""

    try:
        events = read_trace(path, verify=True)
    except (OSError, TraceIntegrityError) as exc:
        typer.echo(f"Trace verification failed: {exc}", err=True)
        raise typer.Exit(5) from exc
    typer.echo(f"Valid trace: {len(events)} events · final hash {events[-1]['event_hash']}")


@app.command("replay-trace")
def replay_trace_command(
    path: Annotated[Path, typer.Argument(help="Complete trace JSONL path.")],
    suite: Annotated[Path, typer.Option(help="Exact scenario suite JSON path.")] = DEFAULT_SUITE,
) -> None:
    """Re-execute recorded tool calls in a fresh sandbox and compare state hashes."""

    loaded = _suite(suite)
    try:
        receipt = replay_trace(path, loaded)
    except (OSError, TraceIntegrityError, ReplayMismatchError) as exc:
        typer.echo(f"Trace replay failed: {exc}", err=True)
        raise typer.Exit(5) from exc
    typer.echo(
        f"Replay matched: {receipt['case_id']} attempt {receipt['attempt']} | "
        f"{receipt['tool_calls']} tool calls | final state {receipt['final_state_hash']}"
    )


@app.command()
def dashboard(
    host: Annotated[str, typer.Option(help="Loopback bind address only.")] = DEFAULT_DASHBOARD_HOST,
    port: Annotated[int, typer.Option(min=1024, max=65535)] = DEFAULT_DASHBOARD_PORT,
) -> None:
    """Serve the read-only, asset-local RTL dashboard."""

    try:
        local_host = require_loopback_host(host)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"Dashboard: http://{local_host}:{port}")
    uvicorn.run(create_dashboard_app(), host=local_host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
