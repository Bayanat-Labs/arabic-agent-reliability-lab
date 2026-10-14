"""Closed, deterministic commerce tool registry.

Scenario files can reference only names registered here. Tool handlers receive a
deep-copied JSON state and either return a result or raise ``ToolRejected`` before
the copy is committed.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from bayanat_lab.schemas import ToolDefinition


class ToolRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


ToolHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler


def validate_tool_arguments(definition: ToolDefinition, arguments: Any) -> None:
    """Validate the small JSON-Schema subset emitted by this registry."""

    if not isinstance(arguments, dict):
        raise ToolRejected("invalid_arguments", "Tool arguments must be a JSON object.")
    schema = definition.input_schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = [key for key in required if key not in arguments]
    if missing:
        raise ToolRejected("invalid_arguments", f"Missing required arguments: {', '.join(missing)}")
    extras = sorted(set(arguments) - set(properties))
    if extras and schema.get("additionalProperties") is False:
        raise ToolRejected("invalid_arguments", f"Unexpected arguments: {', '.join(extras)}")
    type_map = {
        "string": lambda value: isinstance(value, str),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": lambda value: isinstance(value, bool),
    }
    for key, value in arguments.items():
        property_schema = properties.get(key, {})
        expected = property_schema.get("type")
        if expected and expected in type_map and not type_map[expected](value):
            raise ToolRejected(
                "invalid_arguments", f"Argument {key!r} must have JSON type {expected}."
            )
        allowed = property_schema.get("enum")
        if allowed is not None and value not in allowed:
            raise ToolRejected(
                "invalid_arguments",
                f"Argument {key!r} must be one of: {', '.join(map(str, allowed))}.",
            )


def _schema(required: list[str], properties: dict[str, str | dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": {
            key: deepcopy(value) if isinstance(value, dict) else {"type": value}
            for key, value in properties.items()
        },
    }


def _required(args: dict[str, Any], *keys: str) -> None:
    missing = [key for key in keys if key not in args or args[key] in {None, ""}]
    if missing:
        raise ToolRejected("invalid_arguments", f"Missing required arguments: {', '.join(missing)}")


def _authenticated_customer(state: dict[str, Any]) -> str:
    customer_id = state.get("session", {}).get("authenticated_customer_id")
    if not customer_id:
        raise ToolRejected("authentication_required", "لا توجد جلسة عميل موثقة.")
    return str(customer_id)


def _consume_confirmation(
    state: dict[str, Any], action: str, entity_id: str, target: str | None = None
) -> None:
    confirmation = state.get("session", {}).get("confirmation")
    if not isinstance(confirmation, dict):
        raise ToolRejected("confirmation_required", "يلزم تأكيد صريح في خطوة منفصلة.")
    expected = {"action": action, "entity_id": entity_id}
    if target is not None:
        expected["target"] = target
    if confirmation.get("used") or any(
        confirmation.get(key) != value for key, value in expected.items()
    ):
        raise ToolRejected(
            "confirmation_mismatch",
            "التأكيد غير مطابق للإجراء أو الكيان أو الهدف المطلوب.",
        )
    confirmation["used"] = True


def _order(state: dict[str, Any], order_id: str, *, permit_gift: bool = True) -> dict[str, Any]:
    order = state.get("orders", {}).get(order_id)
    if order is None:
        raise ToolRejected("not_found", "الطلب غير موجود.")
    customer_id = _authenticated_customer(state)
    owns_order = order.get("customer_id") == customer_id
    gift_orders = state.get("session", {}).get("valid_gift_receipt_orders", [])
    if not owns_order and not (permit_gift and order_id in gift_orders):
        raise ToolRejected("not_authorized", "الجلسة غير مخولة للوصول إلى هذا الطلب.")
    return order


def _line(order: dict[str, Any], line_id: str) -> dict[str, Any]:
    line = order.get("lines", {}).get(line_id)
    if line is None:
        raise ToolRejected("line_not_found", "سطر الطلب غير موجود.")
    return line


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception as exc:  # pragma: no cover - defensive conversion boundary
        raise ToolRejected("invalid_amount", "المبلغ غير صالح.") from exc


def _inventory_record(state: dict[str, Any], sku: str, variant: str | None) -> dict[str, Any]:
    key = f"{sku}|{variant or ''}"
    record = state.get("inventory", {}).get(key)
    if record is None:
        raise ToolRejected("inventory_not_found", "لا يوجد سجل مخزون مطابق.")
    return record


def get_order(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id")
    order_id = str(args["order_id"])
    order = deepcopy(_order(state, order_id))
    owns_order = order.get("customer_id") == _authenticated_customer(state)
    if not owns_order:
        allowed = {"order_id", "status", "delivered_at", "lines"}
        order = {key: value for key, value in order.items() if key in allowed}
    return {"order": order}


def get_order_timeline(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id")
    order = _order(state, str(args["order_id"]))
    return {
        "status": order.get("status"),
        "expected_delivery": order.get("expected_delivery"),
        "promised_delivery": order.get("promised_delivery"),
        "tracking_event_ar": order.get("tracking_event_ar"),
    }


def list_customer_orders(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    customer_id = _authenticated_customer(state)
    orders = [
        {"order_id": order_id, "status": order.get("status"), "created_at": order.get("created_at")}
        for order_id, order in state.get("orders", {}).items()
        if order.get("customer_id") == customer_id
    ]
    return {"orders": orders, "reliable_latest_order": state.get("reliable_latest_order")}


def get_customer_saved_addresses(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _authenticated_customer(state)
    addresses = [
        {"address_id": address_id, "label_ar": value.get("label_ar")}
        for address_id, value in state.get("saved_addresses", {}).items()
    ]
    return {"addresses": addresses}


def get_inventory(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "sku")
    variant = args.get("variant")
    record = _inventory_record(state, str(args["sku"]), str(variant) if variant else None)
    return {"sku": args["sku"], "variant": variant, **deepcopy(record)}


def get_current_price(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "sku", "variant")
    key = f"{args['sku']}|{args['variant']}"
    price = state.get("catalog_prices", {}).get(key)
    if price is None:
        raise ToolRejected("price_not_found", "لا يوجد سعر حالي مطابق للمنتج والمتغير.")
    return {"sku": args["sku"], "variant": args["variant"], "price": price, "currency": "SAR"}


def get_return_eligibility(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id", "line_id")
    order = _order(state, str(args["order_id"]))
    line = _line(order, str(args["line_id"]))
    eligible = bool(line.get("returnable", True))
    reason = "eligible"
    if line.get("personalized") and not line.get("defective"):
        eligible, reason = False, "personalized_item"
    delivered_at = order.get("delivered_at")
    benchmark_date = state.get("benchmark_date")
    if delivered_at and benchmark_date:
        age = (date.fromisoformat(benchmark_date) - date.fromisoformat(delivered_at)).days
        if age > 14:
            eligible, reason = False, "return_window_expired"
    return {"eligible": eligible, "reason": reason, "line_id": args["line_id"]}


def get_payment_summary(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id")
    _order(state, str(args["order_id"]), permit_gift=False)
    summary = state.get("payment_summaries", {}).get(str(args["order_id"]))
    if summary is None:
        raise ToolRejected("payment_not_found", "لا يوجد ملخص دفع لهذا الطلب.")
    return deepcopy(summary)


def get_membership(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "membership_id")
    membership = state.get("memberships", {}).get(str(args["membership_id"]))
    if not membership:
        raise ToolRejected("not_found", "العضوية غير موجودة.")
    if membership.get("customer_id") != _authenticated_customer(state):
        raise ToolRejected("not_authorized", "الجلسة غير مخولة لهذه العضوية.")
    return {"membership": deepcopy(membership)}


def request_confirmation(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "action", "summary_ar")
    return {"confirmed": False, "status": "awaiting_user", "summary_ar": args["summary_ar"]}


def request_clarification(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "question_ar")
    return {"status": "awaiting_user", "question_ar": args["question_ar"]}


def update_shipping_address(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id", "address_id")
    order = _order(state, str(args["order_id"]), permit_gift=False)
    if order.get("status") != "processing" or order.get("shipping_label_created"):
        raise ToolRejected("address_change_blocked", "لم يعد تغيير العنوان متاحاً لهذه الشحنة.")
    if str(args["address_id"]) not in state.get("saved_addresses", {}):
        raise ToolRejected("address_not_found", "العنوان المحفوظ غير موجود.")
    _consume_confirmation(
        state,
        "update_shipping_address",
        str(args["order_id"]),
        str(args["address_id"]),
    )
    order["shipping_address_id"] = str(args["address_id"])
    return {"updated": True, "order_id": args["order_id"], "address_id": args["address_id"]}


def cancel_order(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id", "reason")
    order = _order(state, str(args["order_id"]), permit_gift=False)
    if (
        order.get("packed")
        or order.get("shipping_label_created")
        or order.get("status") != "processing"
    ):
        raise ToolRejected(
            "cancellation_blocked", "لا يمكن إلغاء الطلب بعد التعبئة أو إنشاء الملصق."
        )
    _consume_confirmation(state, "cancel_order", str(args["order_id"]))
    order["status"] = "cancelled"
    order["refund_status"] = "pending_to_original_payment"
    return {
        "cancelled": True,
        "order_id": args["order_id"],
        "refund_status": order["refund_status"],
        "amount": order.get("paid_amount"),
        "currency": order.get("currency", "SAR"),
    }


def create_return(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id", "line_id", "quantity", "resolution")
    order = _order(state, str(args["order_id"]))
    line = _line(order, str(args["line_id"]))
    eligibility = get_return_eligibility(state, args)
    if not eligibility["eligible"]:
        raise ToolRejected("return_ineligible", f"Return is not eligible: {eligibility['reason']}")
    if any(
        item.get("order_id") == args["order_id"] and item.get("line_id") == args["line_id"]
        for item in state.get("returns", [])
    ):
        raise ToolRejected(
            "duplicate_return", "An active return already exists for this order line."
        )
    quantity = int(args["quantity"])
    if quantity < 1 or quantity > int(line.get("quantity", 0)):
        raise ToolRejected("invalid_quantity", "كمية الإرجاع غير صالحة.")
    if line.get("personalized") and not line.get("defective"):
        raise ToolRejected("return_ineligible", "المنتج المخصص غير قابل للإرجاع دون عيب.")
    if args["resolution"] not in {"refund_original_payment", "gift_credit"}:
        raise ToolRejected("invalid_resolution", "طريقة التسوية غير مسموحة.")
    gift_order = str(args["order_id"]) in state.get("session", {}).get(
        "valid_gift_receipt_orders", []
    )
    if gift_order and args["resolution"] != "gift_credit":
        raise ToolRejected("gift_credit_required", "إرجاع الهدية يعاد كرصيد هدية فقط.")
    line["return_quantity"] = quantity
    line["customer_kept_quantity"] = int(line.get("quantity", 0)) - quantity
    return_id = f"RET-{len(state.setdefault('returns', [])) + 1:04d}"
    state["returns"].append({"return_id": return_id, **deepcopy(args)})
    return {"created": True, "return_id": return_id, **deepcopy(args)}


def create_exchange(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id", "line_id", "target_variant")
    order = _order(state, str(args["order_id"]), permit_gift=False)
    line = _line(order, str(args["line_id"]))
    if line.get("exchange_status") == "created":
        raise ToolRejected("duplicate_exchange", "An exchange already exists for this order line.")
    eligibility = get_return_eligibility(state, args)
    if not eligibility["eligible"]:
        raise ToolRejected(
            "exchange_ineligible", f"Exchange is not eligible: {eligibility['reason']}"
        )
    record = _inventory_record(state, str(line["sku"]), str(args["target_variant"]))
    if int(record.get("available_quantity", 0)) < 1:
        raise ToolRejected("out_of_stock", "المتغير المطلوب غير متوفر.")
    _consume_confirmation(
        state,
        "create_exchange",
        str(args["order_id"]),
        str(args["target_variant"]),
    )
    line["exchange_status"] = "created"
    line["exchange_target_variant"] = str(args["target_variant"])
    state.setdefault("exchanges", []).append(deepcopy(args))
    record["available_quantity"] = int(record.get("available_quantity", 0)) - 1
    return {"created": True, **deepcopy(args)}


def create_replacement(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id", "line_id", "quantity", "replacement_sku")
    order = _order(state, str(args["order_id"]), permit_gift=False)
    line = _line(order, str(args["line_id"]))
    if line.get("replacement_status") == "created":
        raise ToolRejected(
            "duplicate_replacement", "A replacement already exists for this order line."
        )
    if not state.get("damage_evidence", {}).get(str(args["line_id"]), {}).get("verified"):
        raise ToolRejected("evidence_required", "لم يتم التحقق من دليل التلف.")
    if str(args["replacement_sku"]) != str(line.get("sku")):
        raise ToolRejected("replacement_mismatch", "يجب أن يكون البديل مطابقاً للقطعة.")
    record = _inventory_record(state, str(line["sku"]), line.get("variant"))
    if int(record.get("available_quantity", 0)) < int(args["quantity"]):
        raise ToolRejected("out_of_stock", "المخزون لا يكفي لإنشاء البديل.")
    line["replacement_status"] = "created"
    state.setdefault("replacements", []).append(deepcopy(args))
    record["available_quantity"] = int(record.get("available_quantity", 0)) - int(args["quantity"])
    return {"created": True, **deepcopy(args)}


def apply_price_adjustment(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "order_id", "line_id", "amount", "currency")
    order = _order(state, str(args["order_id"]), permit_gift=False)
    line = _line(order, str(args["line_id"]))
    if int(order.get("prior_price_adjustments", 0)) > 0:
        raise ToolRejected("already_adjusted", "تم تطبيق فرق سعر لهذا الطلب من قبل.")
    if not order.get("ordered_at"):
        raise ToolRejected("order_date_missing", "لا يمكن التحقق من نافذة فرق السعر.")
    age = (
        date.fromisoformat(state["benchmark_date"]) - date.fromisoformat(order["ordered_at"])
    ).days
    if age < 0 or age > 7:
        raise ToolRejected("adjustment_window_expired", "انتهت نافذة فرق السعر البالغة سبعة أيام.")
    key = f"{line['sku']}|{line.get('variant', '')}"
    current = state.get("catalog_prices", {}).get(key)
    if current is None:
        raise ToolRejected("price_not_found", "لا يوجد سعر حالي مطابق.")
    expected = _money(line["paid_unit_price"]) - _money(current)
    if _money(args["amount"]) != expected or expected <= 0:
        raise ToolRejected("amount_mismatch", "مبلغ فرق السعر غير مطابق.")
    order["prior_price_adjustments"] = 1
    order["price_adjustment_amount"] = float(expected)
    return {"applied": True, "amount": float(expected), "currency": args["currency"]}


def issue_store_credit(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "customer_id", "amount", "currency", "reason")
    if str(args["customer_id"]) != _authenticated_customer(state):
        raise ToolRejected("not_authorized", "لا يمكن إصدار رصيد لعميل آخر.")
    if args["reason"] != "qualified_late_delivery":
        raise ToolRejected("reason_not_allowed", "سبب الرصيد غير مسموح في هذا المختبر.")
    amount = _money(args["amount"])
    if amount > Decimal("25.00") or amount <= 0:
        raise ToolRejected("credit_cap", "رصيد التأخير يجب ألا يتجاوز 25 SAR.")
    qualifying = None
    benchmark = date.fromisoformat(state["benchmark_date"])
    for order in state.get("orders", {}).values():
        if order.get("customer_id") != args["customer_id"] or not order.get("promised_delivery"):
            continue
        days_late = (benchmark - date.fromisoformat(order["promised_delivery"])).days
        if days_late > 2 and not order.get("late_credit_already_issued"):
            qualifying = order
            break
    if qualifying is None:
        raise ToolRejected("not_eligible", "لا يوجد طلب مؤهل لرصيد التأخير.")
    qualifying["late_credit_already_issued"] = True
    state.setdefault("credits", []).append(deepcopy(args))
    return {"issued": True, "amount": float(amount), "currency": args["currency"]}


def cancel_membership_renewal(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "membership_id")
    membership = state.get("memberships", {}).get(str(args["membership_id"]))
    if not membership or membership.get("customer_id") != _authenticated_customer(state):
        raise ToolRejected("not_authorized", "لا يمكن تعديل هذه العضوية.")
    membership["auto_renew"] = False
    return {
        "updated": True,
        "status": membership.get("status"),
        "benefits_end_at": membership.get("benefits_end_at"),
    }


def create_support_case(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    _required(args, "topic", "order_id", "priority")
    _order(state, str(args["order_id"]), permit_gift=False)
    case_id = f"CASE-{len(state.setdefault('support_cases', [])) + 1:04d}"
    record = {"case_id": case_id, **deepcopy(args), "status": "open"}
    state["support_cases"].append(record)
    return {"created": True, **record}


def _tool(
    name: str,
    description_ar: str,
    mutates: bool,
    required: list[str],
    properties: dict[str, str | dict[str, Any]],
    handler: ToolHandler,
) -> RegisteredTool:
    return RegisteredTool(
        ToolDefinition(
            name=name,
            description_ar=description_ar,
            mutates_state=mutates,
            input_schema=_schema(required, properties),
        ),
        handler,
    )


TOOLS: dict[str, RegisteredTool] = {
    item.definition.name: item
    for item in [
        _tool(
            "get_order",
            "قراءة الطلب المصرح به.",
            False,
            ["order_id"],
            {"order_id": "string"},
            get_order,
        ),
        _tool(
            "get_order_timeline",
            "قراءة حالة ومسار الشحنة.",
            False,
            ["order_id"],
            {"order_id": "string"},
            get_order_timeline,
        ),
        _tool(
            "list_customer_orders", "عرض طلبات العميل الموثق.", False, [], {}, list_customer_orders
        ),
        _tool(
            "get_customer_saved_addresses",
            "عرض معرفات وعناوين الأسماء المحفوظة دون التفاصيل الخاصة.",
            False,
            [],
            {},
            get_customer_saved_addresses,
        ),
        _tool(
            "get_inventory",
            "قراءة مخزون منتج ومتغير محددين.",
            False,
            ["sku"],
            {"sku": "string", "variant": "string"},
            get_inventory,
        ),
        _tool(
            "get_current_price",
            "قراءة السعر الحالي للمنتج والمتغير نفسيهما.",
            False,
            ["sku", "variant"],
            {"sku": "string", "variant": "string"},
            get_current_price,
        ),
        _tool(
            "get_return_eligibility",
            "فحص أهلية إرجاع سطر طلب.",
            False,
            ["order_id", "line_id"],
            {"order_id": "string", "line_id": "string"},
            get_return_eligibility,
        ),
        _tool(
            "get_payment_summary",
            "قراءة ملخص دفع منقح للطلب.",
            False,
            ["order_id"],
            {"order_id": "string"},
            get_payment_summary,
        ),
        _tool(
            "get_membership",
            "قراءة عضوية العميل الموثق.",
            False,
            ["membership_id"],
            {"membership_id": "string"},
            get_membership,
        ),
        _tool(
            "request_confirmation",
            "طلب تأكيد منفصل قبل إجراء حساس.",
            False,
            ["action", "summary_ar"],
            {
                "action": {
                    "type": "string",
                    "enum": [
                        "update_shipping_address",
                        "create_exchange",
                        "cancel_order",
                    ],
                },
                "summary_ar": "string",
            },
            request_confirmation,
        ),
        _tool(
            "request_clarification",
            "طلب معلومة لازمة عند الغموض.",
            False,
            ["question_ar"],
            {"question_ar": "string"},
            request_clarification,
        ),
        _tool(
            "update_shipping_address",
            "تغيير عنوان شحنة مؤهلة بعد التأكيد.",
            True,
            ["order_id", "address_id"],
            {"order_id": "string", "address_id": "string"},
            update_shipping_address,
        ),
        _tool(
            "cancel_order",
            "إلغاء طلب مؤهل بعد التأكيد.",
            True,
            ["order_id", "reason"],
            {
                "order_id": "string",
                "reason": {"type": "string", "enum": ["customer_request"]},
            },
            cancel_order,
        ),
        _tool(
            "create_return",
            "إنشاء إرجاع لسطر وكمية وتسوية محددة.",
            True,
            ["order_id", "line_id", "quantity", "resolution"],
            {
                "order_id": "string",
                "line_id": "string",
                "quantity": "integer",
                "resolution": {
                    "type": "string",
                    "enum": ["refund_original_payment", "gift_credit"],
                },
            },
            create_return,
        ),
        _tool(
            "create_exchange",
            "إنشاء استبدال بمتغير متوفر بعد التأكيد.",
            True,
            ["order_id", "line_id", "target_variant"],
            {"order_id": "string", "line_id": "string", "target_variant": "string"},
            create_exchange,
        ),
        _tool(
            "create_replacement",
            "إنشاء بديل مطابق لتلف موثق.",
            True,
            ["order_id", "line_id", "quantity", "replacement_sku"],
            {
                "order_id": "string",
                "line_id": "string",
                "quantity": "integer",
                "replacement_sku": "string",
            },
            create_replacement,
        ),
        _tool(
            "apply_price_adjustment",
            "تطبيق مبلغ فرق السعر الإيجابي المستحق مرة واحدة.",
            True,
            ["order_id", "line_id", "amount", "currency"],
            {
                "order_id": "string",
                "line_id": "string",
                "amount": "number",
                "currency": {"type": "string", "enum": ["SAR"]},
            },
            apply_price_adjustment,
        ),
        _tool(
            "issue_store_credit",
            "إصدار رصيد تأخير مؤهل ضمن الحد.",
            True,
            ["customer_id", "amount", "currency", "reason"],
            {
                "customer_id": "string",
                "amount": "number",
                "currency": {"type": "string", "enum": ["SAR"]},
                "reason": {
                    "type": "string",
                    "enum": ["qualified_late_delivery"],
                },
            },
            issue_store_credit,
        ),
        _tool(
            "cancel_membership_renewal",
            "إيقاف التجديد القادم مع إبقاء المزايا الحالية.",
            True,
            ["membership_id"],
            {"membership_id": "string"},
            cancel_membership_renewal,
        ),
        _tool(
            "create_support_case",
            "فتح حالة دعم دون الوعد بنتيجتها.",
            True,
            ["topic", "order_id", "priority"],
            {
                "topic": {
                    "type": "string",
                    "enum": [
                        "shipment_intercept_request",
                        "payment_authorization_investigation",
                    ],
                },
                "order_id": "string",
                "priority": {"type": "string", "enum": ["high", "normal", "low"]},
            },
            create_support_case,
        ),
    ]
}


WRITE_TOOLS = {name for name, tool in TOOLS.items() if tool.definition.mutates_state}
