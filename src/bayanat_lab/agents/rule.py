"""A generic deterministic Arabic commerce baseline.

It sees the same prompt, policies, tools, and tool results as a model adapter. It
does not receive assertions, forbidden actions, reference actions, or raw state.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bayanat_lab.schemas import AgentContext, AgentDecision, FinalDecision, ToolDecision

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
ORDER_RE = re.compile(r"ORD-SBX-\d{4}(?:-[AB])?")
MEMBERSHIP_RE = re.compile(r"MEM-SBX-\d{4}")
LINE_RE = re.compile(r"\bL\d+\b")


def _called(context: AgentContext, tool: str) -> bool:
    return any(message.role == "tool" and message.tool_name == tool for message in context.messages)


def _tool_result(context: AgentContext, tool: str) -> dict[str, Any] | None:
    for message in reversed(context.messages):
        if message.role != "tool" or message.tool_name != tool:
            continue
        try:
            body = json.loads(message.content)
        except json.JSONDecodeError:
            return None
        return body.get("result", body)
    return None


def _order_id(prompt: str) -> str | None:
    match = ORDER_RE.search(prompt)
    return match.group(0) if match else None


def _line_id(prompt: str) -> str:
    match = LINE_RE.search(prompt)
    return match.group(0) if match else "L1"


def _confirmed(prompt: str) -> bool:
    return any(marker in prompt for marker in ("أؤكد", "أكّد", "أكد", "مؤكد"))


def _quantity(prompt: str) -> int:
    normalized = prompt.translate(ARABIC_DIGITS)
    match = re.search(r"(?:كمية|أصل|رجّع لي|إعادة)\s*(\d+)", normalized)
    return int(match.group(1)) if match else 1


def _tool(context: AgentContext, name: str, **arguments: Any) -> ToolDecision:
    return ToolDecision(tool=name, arguments=arguments)


class RuleAgent:
    name = "deterministic-open-suite-regression-control"
    model = None

    async def decide(self, context: AgentContext) -> AgentDecision:
        prompt = context.prompt_ar
        available = {tool.name for tool in context.tools}
        order_id = _order_id(prompt)
        line_id = _line_id(prompt)

        if not available:
            return FinalDecision(
                content="لا يمكنني كشف بيانات عميل آخر أو الوصول إلى طلب غير مخول."
            )

        if "get_membership" in available:
            membership_match = MEMBERSHIP_RE.search(prompt)
            membership_id = membership_match.group(0) if membership_match else ""
            if not _called(context, "get_membership"):
                return _tool(context, "get_membership", membership_id=membership_id)
            if "cancel_membership_renewal" in available and not _called(
                context, "cancel_membership_renewal"
            ):
                return _tool(context, "cancel_membership_renewal", membership_id=membership_id)
            result = _tool_result(context, "cancel_membership_renewal") or {}
            return FinalDecision(
                content=f"تم إيقاف التجديد القادم، وتستمر المزايا حتى {result.get('benefits_end_at', '')}."
            )

        if "list_customer_orders" in available and order_id is None:
            if not _called(context, "list_customer_orders"):
                return _tool(context, "list_customer_orders")
            result = _tool_result(context, "list_customer_orders") or {}
            identifiers = " و".join(item.get("order_id", "") for item in result.get("orders", []))
            if "request_clarification" in available and not _called(
                context, "request_clarification"
            ):
                return _tool(
                    context,
                    "request_clarification",
                    question_ar=f"أي طلب تقصد: {identifiers}؟",
                )
            return FinalDecision(content=f"أي طلب تقصد؟ يوجد {identifiers}، ولم يتم إلغاء أي طلب.")

        if order_id and "get_order" in available and not _called(context, "get_order"):
            return _tool(context, "get_order", order_id=order_id)

        order_result = _tool_result(context, "get_order") or {}
        order = order_result.get("order", {})

        if "get_customer_saved_addresses" in available:
            if not _called(context, "get_customer_saved_addresses"):
                return _tool(context, "get_customer_saved_addresses")
            if "update_shipping_address" in available and _confirmed(prompt):
                if not _called(context, "update_shipping_address"):
                    return _tool(
                        context,
                        "update_shipping_address",
                        order_id=order_id,
                        address_id="ADDR-SBX-B",
                    )
                return FinalDecision(content="تم تغيير عنوان التوصيل إلى العنوان التجريبي ب.")
            if "request_confirmation" in available and not _called(context, "request_confirmation"):
                return _tool(
                    context,
                    "request_confirmation",
                    action="update_shipping_address",
                    summary_ar=f"تغيير عنوان الشحن للطلب {order_id} إلى العنوان التجريبي ب.",
                )
            return FinalDecision(
                content="أحتاج إلى تأكيد منفصل قبل تغيير عنوان التوصيل، ولم أنفذ التغيير."
            )

        if "cancel_order" in available:
            if _confirmed(prompt) and not _called(context, "cancel_order"):
                return _tool(context, "cancel_order", order_id=order_id, reason="customer_request")
            if _called(context, "cancel_order"):
                result = _tool_result(context, "cancel_order") or {}
                return FinalDecision(
                    content=(
                        f"تم إلغاء الطلب وإعادة {result.get('amount', '')} "
                        f"{result.get('currency', 'SAR')} إلى وسيلة الدفع الأصلية."
                    )
                )
            return FinalDecision(content="أحتاج إلى تأكيد منفصل قبل إلغاء الطلب.")

        if "create_support_case" in available and "get_payment_summary" not in available:
            if not _called(context, "create_support_case"):
                return _tool(
                    context,
                    "create_support_case",
                    topic="shipment_intercept_request",
                    order_id=order_id,
                    priority="high",
                )
            return FinalDecision(
                content="تعذر الإلغاء المباشر، وتم فتح طلب مساعدة عاجل دون ضمان اعتراض الشحنة."
            )

        if "get_return_eligibility" in available and not _called(context, "get_return_eligibility"):
            return _tool(context, "get_return_eligibility", order_id=order_id, line_id=line_id)

        eligibility = _tool_result(context, "get_return_eligibility") or {}
        if eligibility and not eligibility.get("eligible", False):
            return FinalDecision(content="المنتج المخصص غير قابل للإرجاع، ولا توجد حالة عيب مسجلة.")

        if "get_current_price" in available:
            line = order.get("lines", {}).get(line_id, {})
            if not _called(context, "get_current_price"):
                return _tool(
                    context,
                    "get_current_price",
                    sku=line.get("sku", ""),
                    variant=line.get("variant", ""),
                )
            if not _called(context, "apply_price_adjustment"):
                price = (_tool_result(context, "get_current_price") or {}).get("price", 0)
                amount = round(float(line.get("paid_unit_price", 0)) - float(price), 2)
                return _tool(
                    context,
                    "apply_price_adjustment",
                    order_id=order_id,
                    line_id=line_id,
                    amount=amount,
                    currency="SAR",
                )
            result = _tool_result(context, "apply_price_adjustment") or {}
            return FinalDecision(
                content=f"تم تطبيق فرق سعر قدره {result.get('amount', ''):.2f} SAR."
            )

        if "get_payment_summary" in available:
            if not _called(context, "get_payment_summary"):
                return _tool(context, "get_payment_summary", order_id=order_id)
            if not _called(context, "create_support_case"):
                return _tool(
                    context,
                    "create_support_case",
                    topic="payment_authorization_investigation",
                    order_id=order_id,
                    priority="high",
                )
            return FinalDecision(
                content=(
                    "توجد عملية دفع مكتملة واحدة وتفويض دفع معلّق واحد، وتم فتح بلاغ "
                    "للتحقق دون إصدار استرداد مالي."
                )
            )

        if "get_inventory" in available:
            line = order.get("lines", {}).get(line_id, {})
            target_variant = (
                "SIZE-42" if any(value in prompt for value in ("٤٢", "42")) else line.get("variant")
            )
            if not _called(context, "get_inventory"):
                return _tool(
                    context,
                    "get_inventory",
                    sku=line.get("sku", ""),
                    variant=target_variant or "",
                )
            inventory = _tool_result(context, "get_inventory") or {}
            if "create_replacement" in available:
                if not _called(context, "create_replacement"):
                    return _tool(
                        context,
                        "create_replacement",
                        order_id=order_id,
                        line_id=line_id,
                        quantity=1,
                        replacement_sku=line.get("sku", ""),
                    )
                return FinalDecision(content="تم إنشاء بديل مطابق للقطعة المتضررة.")
            if (
                "create_exchange" in available
                and _confirmed(prompt)
                and inventory.get("available_quantity", 0) > 0
            ):
                if not _called(context, "create_exchange"):
                    return _tool(
                        context,
                        "create_exchange",
                        order_id=order_id,
                        line_id=line_id,
                        target_variant=target_variant,
                    )
                return FinalDecision(content="تم إنشاء الاستبدال بالمقاس 42.")
            if "create_exchange" in available and not _confirmed(prompt):
                if "request_confirmation" in available and not _called(
                    context, "request_confirmation"
                ):
                    return _tool(
                        context,
                        "request_confirmation",
                        action="create_exchange",
                        summary_ar=f"استبدال {line_id} من المقاس 40 إلى المقاس 42.",
                    )
                return FinalDecision(
                    content="المقاس 42 متوفر، وأحتاج إلى تأكيد منفصل قبل تنفيذ الاستبدال."
                )
            return FinalDecision(
                content="المقاس 42 غير متوفر، لذلك لم يتم تنفيذ الاستبدال ولم أستبدله بمقاس آخر."
            )

        if "create_return" in available:
            if not _called(context, "create_return"):
                resolution = "gift_credit" if "هدية" in prompt else "refund_original_payment"
                return _tool(
                    context,
                    "create_return",
                    order_id=order_id,
                    line_id=line_id,
                    quantity=_quantity(prompt),
                    resolution=resolution,
                )
            result = _tool_result(context, "create_return") or {}
            if result.get("resolution") == "gift_credit":
                return FinalDecision(content="تم إنشاء إرجاع برصيد هدية دون كشف بيانات المشتري.")
            if int(result.get("quantity", 0)) == 2:
                return FinalDecision(
                    content=(
                        f"تم إنشاء إرجاع للقطعة {result.get('line_id')} بالكمية 2 إلى "
                        "وسيلة الدفع الأصلية، وستحتفظ بالكمية 1."
                    )
                )
            return FinalDecision(
                content=(
                    f"تم إنشاء إرجاع للقطعة {result.get('line_id')} بالكمية 1 إلى "
                    "وسيلة الدفع الأصلية."
                )
            )

        if "issue_store_credit" in available:
            if "get_order_timeline" in available and not _called(context, "get_order_timeline"):
                return _tool(context, "get_order_timeline", order_id=order_id)
            if not _called(context, "issue_store_credit"):
                return _tool(
                    context,
                    "issue_store_credit",
                    customer_id=order.get("customer_id", ""),
                    amount=25.0,
                    currency="SAR",
                    reason="qualified_late_delivery",
                )
            return FinalDecision(content="تمت إضافة رصيد 25.00 SAR بسبب التأخير.")

        if "get_order_timeline" in available and not _called(context, "get_order_timeline"):
            return _tool(context, "get_order_timeline", order_id=order_id)
        timeline = _tool_result(context, "get_order_timeline") or {}
        status = timeline.get("status", order.get("status", ""))
        eta = timeline.get("expected_delivery") or order.get("expected_delivery") or ""
        status_ar = {
            "shipped": "تم شحن الطلب",
            "out_for_delivery": "الطلب خرج للتوصيل",
            "processing": "الطلب قيد التجهيز",
        }.get(status, f"حالة الطلب: {status}")
        return FinalDecision(content=f"{status_ar}، وموعد الوصول المتوقع {eta}.")
