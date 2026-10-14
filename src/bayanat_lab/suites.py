"""Scenario-suite loading, validation, selection, and content hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from bayanat_lab.schemas import ScenarioSpec, ScenarioSuite
from bayanat_lab.tools import TOOLS


class SuiteValidationError(ValueError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_suite(path: Path) -> ScenarioSuite:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SuiteValidationError(f"Suite not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SuiteValidationError(f"Invalid JSON in {path}: {exc}") from exc
    try:
        suite = ScenarioSuite.model_validate(raw)
    except ValidationError as exc:
        raise SuiteValidationError(str(exc)) from exc
    for scenario in suite.scenarios:
        if not scenario.policy_ar:
            scenario.policy_ar = list(suite.metadata.policy_ar)
    validate_suite_contract(suite)
    return suite


def validate_suite_contract(suite: ScenarioSuite) -> None:
    errors: list[str] = []
    security_pairs: dict[str, set[str]] = {}
    for scenario in suite.scenarios:
        unknown = sorted(set(scenario.allowed_tools) - set(TOOLS))
        if unknown:
            errors.append(f"{scenario.id}: unknown allowed tools: {', '.join(unknown)}")
        for assertion in scenario.assertions:
            if assertion.tool and assertion.tool not in TOOLS:
                errors.append(f"{scenario.id}: assertion references unknown tool {assertion.tool}")
        for forbidden in scenario.forbidden_actions:
            if forbidden.tool != "*" and forbidden.tool not in TOOLS:
                errors.append(
                    f"{scenario.id}: forbidden rule references unknown tool {forbidden.tool}"
                )
        for action in scenario.reference_actions:
            if action.kind == "tool":
                if not action.tool:
                    errors.append(f"{scenario.id}: reference tool action has no tool name")
                elif action.tool not in scenario.allowed_tools:
                    errors.append(
                        f"{scenario.id}: reference action uses disallowed tool {action.tool}"
                    )
            elif not action.content:
                errors.append(f"{scenario.id}: reference final action has no content")
        if scenario.security_probe:
            probe = scenario.security_probe
            security_pairs.setdefault(probe.pair_id, set()).add(probe.condition)
            exposed = next(
                (
                    item
                    for item in scenario.context_items
                    if item.id == probe.exposed_context_id
                ),
                None,
            )
            if exposed is None or exposed.trust != "untrusted":
                errors.append(
                    f"{scenario.id}: security probe context must be present and untrusted"
                )
    for pair_id, conditions in security_pairs.items():
        expected = {"benign_control", "adversarial_injection"}
        if conditions != expected:
            errors.append(
                f"security probe {pair_id}: expected paired conditions {sorted(expected)}, "
                f"observed {sorted(conditions)}"
            )
    if errors:
        raise SuiteValidationError("\n".join(errors))


def select_scenarios(
    suite: ScenarioSuite,
    scenario_ids: list[str] | None = None,
    register: str | None = None,
    limit: int | None = None,
) -> list[ScenarioSpec]:
    selected = suite.scenarios
    if scenario_ids:
        wanted = set(scenario_ids)
        selected = [scenario for scenario in selected if scenario.id in wanted]
        missing = sorted(wanted - {scenario.id for scenario in selected})
        if missing:
            raise SuiteValidationError(f"Unknown scenario IDs: {', '.join(missing)}")
    if register:
        selected = [scenario for scenario in selected if scenario.language_register == register]
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise SuiteValidationError("Scenario selection is empty")
    return selected
