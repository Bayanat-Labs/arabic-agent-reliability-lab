"""Explicit harness oracle for tests; never a comparable benchmark system."""

from __future__ import annotations

from bayanat_lab.schemas import (
    AgentContext,
    AgentDecision,
    FinalDecision,
    ReferenceAction,
    ToolDecision,
)


class ReferenceAgent:
    name = "reference-oracle-not-a-benchmark"
    model = None

    def __init__(self, actions: list[ReferenceAction]) -> None:
        self.actions = actions

    async def decide(self, context: AgentContext) -> AgentDecision:
        index = len([message for message in context.messages if message.role == "assistant"])
        if index >= len(self.actions):
            return FinalDecision(content="اكتمل السيناريو المرجعي.")
        action = self.actions[index]
        if action.kind == "tool":
            assert action.tool is not None
            return ToolDecision(tool=action.tool, arguments=action.arguments)
        return FinalDecision(content=action.content or "اكتمل السيناريو المرجعي.")
