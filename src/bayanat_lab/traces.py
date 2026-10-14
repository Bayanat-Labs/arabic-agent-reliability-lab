"""UTF-8 JSONL traces protected by a SHA-256 hash chain."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from bayanat_lab.sandbox import canonical_json

ZERO_HASH = "0" * 64


class TraceIntegrityError(ValueError):
    pass


class TraceWriter:
    def __init__(self, path: Path, run_id: str, case_id: str, attempt: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.run_id = run_id
        self.case_id = case_id
        self.attempt = attempt
        self.seq = 0
        self.previous_hash = ZERO_HASH
        self._stream = path.open("w", encoding="utf-8", newline="\n")

    def write(
        self, event_type: str, payload: dict[str, Any], elapsed_ms: float = 0.0
    ) -> dict[str, Any]:
        self.seq += 1
        event = {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "case_id": self.case_id,
            "attempt": self.attempt,
            "seq": self.seq,
            "event_type": event_type,
            "logical_time": f"T+{self.seq:04d}",
            "elapsed_ms": round(float(elapsed_ms), 3),
            "payload": payload,
            "previous_hash": self.previous_hash,
        }
        event_hash = hashlib.sha256(canonical_json(event).encode("utf-8")).hexdigest()
        event["event_hash"] = event_hash
        self._stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self.previous_hash = event_hash
        return event

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def read_trace(path: Path, *, verify: bool = True) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous_hash = ZERO_HASH
    identity: tuple[Any, Any, Any] | None = None
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TraceIntegrityError(f"Invalid JSON at line {line_number}") from exc
            if verify:
                current_identity = (
                    event.get("run_id"),
                    event.get("case_id"),
                    event.get("attempt"),
                )
                if identity is None:
                    identity = current_identity
                elif current_identity != identity:
                    raise TraceIntegrityError(f"Trace identity changed at line {line_number}")
                if event.get("seq") != line_number:
                    raise TraceIntegrityError(f"Non-contiguous sequence at line {line_number}")
                if event.get("previous_hash") != previous_hash:
                    raise TraceIntegrityError(f"Broken previous hash at line {line_number}")
                claimed = event.get("event_hash")
                unsigned = {key: value for key, value in event.items() if key != "event_hash"}
                actual = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
                if claimed != actual:
                    raise TraceIntegrityError(f"Invalid event hash at line {line_number}")
                previous_hash = claimed
            events.append(event)
    if not events:
        raise TraceIntegrityError("Trace is empty")
    if verify:
        if events[0].get("event_type") != "case_started":
            raise TraceIntegrityError("Trace has no case_started boundary")
        if events[-1].get("event_type") != "case_finished":
            raise TraceIntegrityError("Trace is a valid prefix but has no case_finished boundary")
    return events
