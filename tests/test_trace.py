import json

import pytest

from bayanat_lab.traces import TraceIntegrityError, TraceWriter, read_trace


def test_trace_hash_chain_accepts_arabic(tmp_path):
    path = tmp_path / "trace.jsonl"
    with TraceWriter(path, "RUN-1", "BARL-COM-001", 1) as trace:
        trace.write("case_started", {"prompt": "وش صار على طلبي؟"})
        trace.write("case_finished", {"response": "تم شحن الطلب"})
    events = read_trace(path)
    assert len(events) == 2
    assert events[-1]["payload"]["response"] == "تم شحن الطلب"


def test_tampered_trace_is_rejected(tmp_path):
    path = tmp_path / "trace.jsonl"
    with TraceWriter(path, "RUN-1", "BARL-COM-001", 1) as trace:
        trace.write("case_started", {"safe": True})
        trace.write("case_finished", {"safe": True})
    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    event["payload"]["safe"] = False
    lines[0] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TraceIntegrityError, match="Invalid event hash"):
        read_trace(path)
