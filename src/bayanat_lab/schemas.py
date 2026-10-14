"""Versioned, closed schemas for scenarios, decisions, traces, and results."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)


class Severity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    PROCEDURAL = "procedural"
    INTERACTION = "interaction"


class AssertionType(StrEnum):
    STATE_EQUALS = "state_equals"
    STATE_UNCHANGED = "state_unchanged"
    TOOL_CALLED = "tool_called"
    TOOL_SUCCEEDED = "tool_succeeded"
    TOOL_CALLED_EXACTLY_ONCE = "tool_called_exactly_once"
    TOOL_NOT_CALLED = "tool_not_called"
    RESPONSE_CONTAINS_ANY = "response_contains_any"
    RESPONSE_CONTAINS_ALL = "response_contains_all"
    RESPONSE_OMITS = "response_omits"
    RESPONSE_REFUSES = "response_refuses"


class Outcome(StrEnum):
    PASS = "pass"
    TASK_FAIL = "task_fail"
    UNSAFE_FAIL = "unsafe_fail"
    AGENT_ERROR = "agent_error"
    INFRA_ERROR = "infra_error"
    INVALID_CASE = "invalid_case"


class ToolAccessMode(StrEnum):
    """Which registered tools are disclosed and executable during an episode."""

    LEAST_PRIVILEGE = "least_privilege"
    FULL_TOOLSET = "full_toolset"


class AssertionSpec(StrictModel):
    type: AssertionType
    description_ar: str
    severity: Severity = Severity.MAJOR
    path: str | None = None
    expected: Any = None
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fields(self) -> AssertionSpec:
        if self.type == AssertionType.STATE_EQUALS and not self.path:
            raise ValueError("state_equals requires path")
        if self.type == AssertionType.STATE_UNCHANGED and not self.path:
            self.path = "$"
        if (
            self.type
            in {
                AssertionType.TOOL_CALLED,
                AssertionType.TOOL_SUCCEEDED,
                AssertionType.TOOL_CALLED_EXACTLY_ONCE,
                AssertionType.TOOL_NOT_CALLED,
            }
            and not self.tool
        ):
            raise ValueError(f"{self.type} requires tool")
        if (
            self.type
            in {
                AssertionType.RESPONSE_CONTAINS_ANY,
                AssertionType.RESPONSE_CONTAINS_ALL,
                AssertionType.RESPONSE_OMITS,
            }
            and not self.values
        ):
            raise ValueError(f"{self.type} requires values")
        return self


class ForbiddenActionSpec(StrictModel):
    tool: str
    description_ar: str
    severity: Severity
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_gt: dict[str, float] = Field(default_factory=dict)
    count_rejected_attempt: bool = True


class ContextItem(StrictModel):
    """Declared context delivered to the agent before its first decision."""

    id: str
    source: str
    trust: Literal["trusted", "untrusted"]
    content: str


class SecurityProbeSpec(StrictModel):
    """Metadata for a paired benign/adversarial security probe."""

    pair_id: str
    condition: Literal["benign_control", "adversarial_injection"]
    exposed_context_id: str


class ReferenceAction(StrictModel):
    """Harness-oracle action; never exposed in an AgentContext."""

    kind: Literal["tool", "final"]
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    content: str | None = None


class ScenarioSpec(StrictModel):
    id: str = Field(pattern=r"^BARL-COM-\d{3}$")
    version: int = 1
    title_ar: str
    title_en: str
    domain: Literal["rtl_commerce"] = "rtl_commerce"
    locale: str = "ar-SA"
    language_register: Literal["msa", "saudi_oriented_colloquial"] = Field(alias="register")
    dialect_validation: Literal["not_applicable_msa", "unvalidated_native_review_required"]
    origin: Literal["synthetic"]
    review_status: Literal["unreviewed", "single_reviewed", "double_reviewed", "adjudicated"]
    prompt_ar: str
    context_items: list[ContextItem] = Field(default_factory=list)
    security_probe: SecurityProbeSpec | None = None
    policy_ar: list[str] = Field(default_factory=list)
    max_steps: int = Field(default=8, ge=1, le=20)
    initial_state: dict[str, Any]
    allowed_tools: list[str]
    assertions: list[AssertionSpec]
    forbidden_actions: list[ForbiddenActionSpec] = Field(default_factory=list)
    tags: list[str]
    reference_actions: list[ReferenceAction] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_language_status(self) -> ScenarioSpec:
        if (
            self.language_register == "saudi_oriented_colloquial"
            and self.dialect_validation != "unvalidated_native_review_required"
        ):
            raise ValueError("Saudi-oriented content must remain explicitly unvalidated")
        if len(self.allowed_tools) != len(set(self.allowed_tools)):
            raise ValueError("allowed_tools contains duplicates")
        context_ids = [item.id for item in self.context_items]
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("context_items contains duplicate IDs")
        if self.security_probe and self.security_probe.exposed_context_id not in context_ids:
            raise ValueError("security_probe must reference a declared context item")
        return self


class SuiteMetadata(StrictModel):
    id: str
    version: str
    name_ar: str
    name_en: str
    split: Literal["open", "heldout"]
    license: str
    fictional: bool = True
    validation_notice_ar: str
    policy_ar: list[str]
    creation_date: str
    authoring_method: str
    rights_owner: str
    methodology_status: Literal["engineering_preview"] = "engineering_preview"


class ScenarioSuite(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    metadata: SuiteMetadata
    scenarios: list[ScenarioSpec]

    @model_validator(mode="after")
    def unique_ids(self) -> ScenarioSuite:
        ids = [scenario.id for scenario in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario IDs must be unique")
        return self


class ToolDefinition(StrictModel):
    name: str
    description_ar: str
    mutates_state: bool
    input_schema: dict[str, Any]


class AgentMessage(StrictModel):
    role: Literal["assistant", "tool"]
    content: str
    tool_name: str | None = None


class AgentContext(StrictModel):
    scenario_id: str
    prompt_ar: str
    policy_ar: list[str]
    locale: str
    language_register: str = Field(alias="register")
    context_items: list[ContextItem] = Field(default_factory=list)
    tools: list[ToolDefinition]
    messages: list[AgentMessage]
    step: int
    max_steps: int


class ToolDecision(StrictModel):
    kind: Literal["tool"] = "tool"
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class FinalDecision(StrictModel):
    kind: Literal["final"] = "final"
    content: str


AgentDecision = Annotated[ToolDecision | FinalDecision, Field(discriminator="kind")]


class ToolExecution(StrictModel):
    seq: int
    tool: str
    arguments: dict[str, Any]
    status: Literal["ok", "rejected", "error"]
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    mutated_state: bool = False
    elapsed_ms: float = 0.0


class AssertionResult(StrictModel):
    assertion: AssertionSpec
    passed: bool
    observed: Any = None


class SafetyViolation(StrictModel):
    rule: ForbiddenActionSpec
    matched_call: ToolExecution


class SafetyRuleResult(StrictModel):
    """Opportunity-aware observation for one prohibited-action rule."""

    rule: ForbiddenActionSpec
    origin: Literal["scenario", "duplicate_write_guard"] = "scenario"
    tool_available: bool
    proposed: int = 0
    blocked: int = 0
    execution_error: int = 0
    executed: int = 0


class CaseResult(StrictModel):
    schema_version: Literal["1.0", "1.1"] = "1.1"
    run_id: str
    scenario_id: str
    attempt: int
    outcome: Outcome
    language_register: str = Field(alias="register")
    dialect_validation: str
    tags: list[str]
    agent_name: str
    model: str | None = None
    final_response: str = ""
    steps: int
    elapsed_ms: float
    initial_state_hash: str
    final_state_hash: str
    assertion_results: list[AssertionResult]
    safety_violations: list[SafetyViolation]
    operational_pass: bool | None = None
    communication_pass: bool | None = None
    tool_access_mode: ToolAccessMode = ToolAccessMode.LEAST_PRIVILEGE
    exposed_tools: list[str] = Field(default_factory=list)
    exposed_context_ids: list[str] = Field(default_factory=list)
    safety_rule_results: list[SafetyRuleResult] = Field(default_factory=list)
    tool_executions: list[ToolExecution]
    agent_error: str | None = None
    infra_error: str | None = None


class Passport(StrictModel):
    schema_version: Literal["1.0", "1.1"] = "1.1"
    run_id: str
    generated_at: str
    research_status: Literal["engineering_preview"] = "engineering_preview"
    system_snapshot: dict[str, Any]
    counts: dict[str, int]
    metrics: dict[str, Any]
    slices: dict[str, Any]
    warnings: list[str]
    cases: list[dict[str, Any]]
