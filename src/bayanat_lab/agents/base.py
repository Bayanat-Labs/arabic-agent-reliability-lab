"""Minimal adapter protocol shared by local agent implementations."""

from __future__ import annotations

from typing import Protocol

from bayanat_lab.schemas import AgentContext, AgentDecision


class AgentRuntimeError(RuntimeError):
    """Local inference service/model failed independently of agent behavior."""


class AgentProtocolError(ValueError):
    """The model returned a response that violates the adapter contract."""


class AgentAdapter(Protocol):
    name: str
    model: str | None

    async def decide(self, context: AgentContext) -> AgentDecision:
        """Return one tool call or a final answer."""
