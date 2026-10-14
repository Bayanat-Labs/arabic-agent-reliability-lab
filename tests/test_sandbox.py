from bayanat_lab.sandbox import Sandbox, initialize_database, state_hash


def _address_state(confirmed: bool):
    return {
        "session": {
            "authenticated_customer_id": "CUST-SBX-TEST",
            "confirmation": (
                {
                    "action": "update_shipping_address",
                    "entity_id": "ORD-SBX-TEST",
                    "target": "ADDR-B",
                    "used": False,
                }
                if confirmed
                else None
            ),
        },
        "orders": {
            "ORD-SBX-TEST": {
                "order_id": "ORD-SBX-TEST",
                "customer_id": "CUST-SBX-TEST",
                "status": "processing",
                "shipping_label_created": False,
                "shipping_address_id": "ADDR-A",
            }
        },
        "saved_addresses": {
            "ADDR-A": {"label_ar": "المنزل"},
            "ADDR-B": {"label_ar": "العمل"},
        },
    }


def test_resets_are_identical_and_unicode_survives(tmp_path):
    state = _address_state(False)
    state["note_ar"] = "طلب رقم ٤٢ — أهلاً وسهلاً"
    first = tmp_path / "first.sqlite3"
    second = tmp_path / "second.sqlite3"
    initialize_database(first, state)
    initialize_database(second, state)
    first_state = Sandbox(first, ["get_order"]).snapshot()
    second_state = Sandbox(second, ["get_order"]).snapshot()
    assert state_hash(first_state) == state_hash(second_state)
    assert first_state["note_ar"] == "طلب رقم ٤٢ — أهلاً وسهلاً"


def test_sensitive_mutation_is_atomic_and_confirmation_bound(tmp_path):
    db = tmp_path / "case.sqlite3"
    initialize_database(db, _address_state(False))
    sandbox = Sandbox(db, ["update_shipping_address"])
    before = sandbox.hash()
    rejected = sandbox.execute(
        "update_shipping_address", {"order_id": "ORD-SBX-TEST", "address_id": "ADDR-B"}
    )
    assert rejected.status == "rejected"
    assert sandbox.hash() == before
    assert sandbox.snapshot()["orders"]["ORD-SBX-TEST"]["shipping_address_id"] == "ADDR-A"


def test_unknown_or_disallowed_tools_never_mutate_state(tmp_path):
    db = tmp_path / "case.sqlite3"
    initialize_database(db, _address_state(True))
    sandbox = Sandbox(db, ["get_order"])
    before = sandbox.hash()
    execution = sandbox.execute(
        "update_shipping_address", {"order_id": "ORD-SBX-TEST", "address_id": "ADDR-B"}
    )
    assert execution.status == "rejected"
    assert sandbox.hash() == before


def test_confirmed_address_change_commits_once(tmp_path):
    db = tmp_path / "case.sqlite3"
    initialize_database(db, _address_state(True))
    sandbox = Sandbox(db, ["update_shipping_address"])
    execution = sandbox.execute(
        "update_shipping_address", {"order_id": "ORD-SBX-TEST", "address_id": "ADDR-B"}
    )
    assert execution.status == "ok"
    assert execution.mutated_state
    assert sandbox.snapshot()["orders"]["ORD-SBX-TEST"]["shipping_address_id"] == "ADDR-B"


def test_finite_tool_values_are_declared_and_enforced(tmp_path, suite):
    scenario = next(item for item in suite.scenarios if item.id == "BARL-COM-006")
    db = tmp_path / "case.sqlite3"
    initialize_database(db, scenario.initial_state)
    sandbox = Sandbox(db, scenario.allowed_tools)

    execution = sandbox.execute(
        "create_return",
        {
            "order_id": "ORD-SBX-1006",
            "line_id": "L2",
            "quantity": 1,
            "resolution": "refund",
        },
    )

    assert execution.status == "rejected"
    assert execution.error and "must be one of" in execution.error
    assert sandbox.snapshot()["returns"] == []
