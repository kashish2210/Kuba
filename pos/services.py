"""Pure helpers for POS: payment defaults, order numbering, totals, serialisation."""
from decimal import ROUND_HALF_UP, Decimal

from cafe_pos.models import Order, PaymentMethod, POSSession

CENTS = Decimal("0.01")
DEFAULT_METHODS = [("cash", True), ("card", False), ("upi", False)]


def ensure_payment_methods(cafe):
    """Guarantee the three payment methods exist for a cafe (cash on by default)."""
    for method_type, enabled in DEFAULT_METHODS:
        PaymentMethod.objects.get_or_create(
            cafe=cafe, type=method_type, defaults={"is_enabled": enabled}
        )
    return PaymentMethod.objects.filter(cafe=cafe).order_by("type")


def current_session(cafe):
    return POSSession.objects.filter(cafe=cafe, status="open").first()


def open_session(cafe, user):
    session = current_session(cafe)
    if session:
        return session
    return POSSession.objects.create(cafe=cafe, opened_by=user, status="open")


def next_order_number(cafe):
    n = Order.objects.filter(cafe=cafe).count() + 1
    while Order.objects.filter(cafe=cafe, order_number=f"ORD-{n:04d}").exists():
        n += 1
    return f"ORD-{n:04d}"


def _q(value):
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def recalc_order(order):
    """Recompute and persist subtotal / tax / total from the order's lines.

    subtotal = Σ line_total (line_total = unit_price·qty − line_discount)
    tax      = Σ (unit_price·qty · product.tax_percentage%)
    total    = subtotal + tax − discount_amount   (clamped ≥ 0)
    """
    subtotal = Decimal("0")
    tax = Decimal("0")
    for line in order.line_items.select_related("product"):
        base = line.unit_price * line.quantity
        line_total = base - line.line_discount
        if line.line_total != line_total:
            line.line_total = line_total
            line.save(update_fields=["line_total"])
        subtotal += line_total
        tax += base * (line.product.tax_percentage / Decimal("100"))

    discount = order.discount_amount or Decimal("0")
    total = subtotal + tax - discount
    if total < 0:
        total = Decimal("0")

    order.subtotal = _q(subtotal)
    order.tax_amount = _q(tax)
    order.total = _q(total)
    order.save(update_fields=["subtotal", "tax_amount", "total"])
    return order


def order_json(order):
    lines = []
    for line in order.line_items.select_related("product").order_by("id"):
        lines.append({
            "id": line.id,
            "product_id": line.product_id,
            "name": line.product.name,
            "unit_price": float(line.unit_price),
            "quantity": line.quantity,
            "line_total": float(line.line_total),
            "tax_percentage": float(line.product.tax_percentage),
        })
    customer = None
    if order.customer_id:
        customer = {
            "id": order.customer_id,
            "name": order.customer.name,
            "phone": order.customer.phone or "",
            "email": order.customer.email or "",
        }
    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "table_id": order.table_id,
        "table_number": order.table.table_number if order.table_id else None,
        "customer": customer,
        "lines": lines,
        "subtotal": float(order.subtotal),
        "tax_amount": float(order.tax_amount),
        "discount_amount": float(order.discount_amount or 0),
        "total": float(order.total),
        "created_at": order.created_at.strftime("%d/%m %H:%M"),
    }


def upi_qr_payload(upi_id, amount, name=""):
    payload = f"upi://pay?pa={upi_id}&am={amount}&cu=INR"
    if name:
        payload += f"&pn={name}"
    return payload
