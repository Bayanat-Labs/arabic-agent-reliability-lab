"""Resettable SQLite state store and in-process FastAPI tool surface."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from bayanat_lab.schemas import ToolExecution
from bayanat_lab.tools import TOOLS, ToolRejected, validate_tool_arguments


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def state_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalized_initial_state(value: dict[str, Any]) -> dict[str, Any]:
    state = deepcopy(value)
    state.setdefault("benchmark_date", "2026-08-05")
    state.setdefault("session", {})
    state.setdefault("orders", {})
    state.setdefault("saved_addresses", {})
    state.setdefault("inventory", {})
    state.setdefault("catalog_prices", {})
    state.setdefault("payment_summaries", {})
    state.setdefault("memberships", {})
    state.setdefault("returns", [])
    state.setdefault("exchanges", [])
    state.setdefault("replacements", [])
    state.setdefault("credits", [])
    state.setdefault("support_cases", [])
    return state


def initialize_database(path: Path, initial_state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE state (id INTEGER PRIMARY KEY CHECK (id = 1), body TEXT NOT NULL)"
        )
        connection.execute(
            """CREATE TABLE audit (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                tool TEXT NOT NULL,
                arguments TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT NOT NULL,
                error TEXT,
                mutated_state INTEGER NOT NULL,
                elapsed_ms REAL NOT NULL
            )"""
        )
        state = normalized_initial_state(initial_state)
        connection.execute("INSERT INTO state(id, body) VALUES (1, ?)", (canonical_json(state),))
        connection.commit()


class Sandbox:
    def __init__(self, db_path: Path, allowed_tools: list[str]) -> None:
        unknown = sorted(set(allowed_tools) - set(TOOLS))
        if unknown:
            raise ValueError(f"Unknown tools in scenario: {', '.join(unknown)}")
        self.db_path = db_path
        self.allowed_tools = frozenset(allowed_tools)

    def snapshot(self) -> dict[str, Any]:
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            row = connection.execute("SELECT body FROM state WHERE id = 1").fetchone()
        if row is None:
            raise RuntimeError("Sandbox state row is missing")
        return json.loads(row[0])

    def hash(self) -> str:
        return state_hash(self.snapshot())

    def audit(self) -> list[ToolExecution]:
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            rows = connection.execute(
                "SELECT seq, tool, arguments, status, result, error, mutated_state, elapsed_ms "
                "FROM audit ORDER BY seq"
            ).fetchall()
        return [
            ToolExecution(
                seq=row[0],
                tool=row[1],
                arguments=json.loads(row[2]),
                status=row[3],
                result=json.loads(row[4]),
                error=row[5],
                mutated_state=bool(row[6]),
                elapsed_ms=float(row[7]),
            )
            for row in rows
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecution:
        started = time.perf_counter()
        status = "ok"
        result: dict[str, Any] = {}
        error: str | None = None
        mutated = False
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            body = connection.execute("SELECT body FROM state WHERE id = 1").fetchone()
            if body is None:
                raise RuntimeError("Sandbox state row is missing")
            before = json.loads(body[0])
            after = deepcopy(before)
            try:
                if tool_name not in TOOLS:
                    raise ToolRejected("unknown_tool", f"Unknown tool: {tool_name}")
                if tool_name not in self.allowed_tools:
                    raise ToolRejected(
                        "tool_not_allowed", f"Tool is not allowed in this scenario: {tool_name}"
                    )
                validate_tool_arguments(TOOLS[tool_name].definition, arguments)
                result = TOOLS[tool_name].handler(after, deepcopy(arguments))
                mutated = state_hash(before) != state_hash(after)
                if mutated:
                    connection.execute(
                        "UPDATE state SET body = ? WHERE id = 1", (canonical_json(after),)
                    )
            except ToolRejected as exc:
                status = "rejected"
                error = f"{exc.code}: {exc.message}"
            except Exception as exc:  # pragma: no cover - infrastructure boundary
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
            elapsed_ms = (time.perf_counter() - started) * 1000
            cursor = connection.execute(
                "INSERT INTO audit(tool, arguments, status, result, error, mutated_state, elapsed_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    tool_name,
                    canonical_json(arguments),
                    status,
                    canonical_json(result),
                    error,
                    int(mutated),
                    elapsed_ms,
                ),
            )
            connection.commit()
        return ToolExecution(
            seq=int(cursor.lastrowid),
            tool=tool_name,
            arguments=deepcopy(arguments),
            status=status,
            result=result,
            error=error,
            mutated_state=mutated,
            elapsed_ms=elapsed_ms,
        )


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)


def create_sandbox_app(sandbox: Sandbox) -> FastAPI:
    """Create an HTTP contract used through ASGITransport during benchmark runs."""

    app = FastAPI(title="Bayanat synthetic commerce sandbox", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "state_hash": sandbox.hash()}

    @app.get("/tools")
    def tools() -> dict[str, Any]:
        return {
            "tools": [
                TOOLS[name].definition.model_dump(mode="json")
                for name in sorted(sandbox.allowed_tools)
            ]
        }

    @app.post("/tools/{tool_name}")
    def execute_tool(tool_name: str, request: ToolRequest) -> dict[str, Any]:
        execution = sandbox.execute(tool_name, request.arguments)
        return {"ok": execution.status == "ok", "execution": execution.model_dump(mode="json")}

    return app
