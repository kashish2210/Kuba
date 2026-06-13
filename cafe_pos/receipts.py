"""Receipt rendering + emailing (default design or per-cafe custom HTML)."""
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template import Context, Template
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

# Draggable "data pills" exposed in the receipt editor. (token, label)
DATA_PILLS = [
    ("order_number", "Order #"),
    ("cafe_name", "Cafe name"),
    ("table", "Table"),
    ("customer_name", "Customer"),
    ("date", "Date / time"),
    ("payment_method", "Payment method"),
    ("subtotal", "Subtotal"),
    ("tax", "Tax"),
    ("discount", "Discount"),
    ("total", "Total"),
    ("items_table", "Items table"),
    ("review_url", "Review link"),
    ("logo", "Logo"),
]


def _money(value):
    return f"₹{Decimal(value or 0):.2f}"


def order_context(order, request=None):
    cafe = order.cafe
    lines = list(order.line_items.select_related("product").all())
    rows = "".join(
        f"<tr><td style='padding:4px 0'>{l.product.name}</td>"
        f"<td style='text-align:center'>{l.quantity}</td>"
        f"<td style='text-align:right'>{_money(l.line_total)}</td></tr>"
        for l in lines
    )
    items_table = (
        "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
        "<thead><tr style='border-bottom:1px solid #ddd'>"
        "<th style='text-align:left;padding-bottom:6px'>Item</th>"
        "<th style='padding-bottom:6px'>Qty</th>"
        "<th style='text-align:right;padding-bottom:6px'>Amount</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    method = getattr(getattr(order, "payment_record", None), "method_type", "") or ""
    review_path = reverse("pos:order-review", args=[order.review_token])
    if request is not None:
        review_url = request.build_absolute_uri(review_path)
    else:
        review_url = order.cafe.dashboard_url().rstrip("/") + review_path
    return {
        "order_number": order.order_number,
        "cafe_name": cafe.name,
        "table": order.table.table_number if order.table_id else "—",
        "customer_name": order.customer.name if order.customer_id else "Walk-in",
        "date": timezone.localtime(order.paid_at or order.created_at).strftime("%d %b %Y, %I:%M %p"),
        "payment_method": method.upper(),
        "subtotal": _money(order.subtotal),
        "tax": _money(order.tax_amount),
        "discount": _money(order.discount_amount or 0),
        "total": _money(order.total),
        "items": lines,
        "items_table": items_table,
        "review_url": review_url,
        "logo": cafe.logo_svg or "",
        "cafe": cafe,
        "order": order,
    }


def render_receipt(order, request=None):
    """Custom cafe HTML (with data pills) if set, else the built-in default design."""
    from .models import ReceiptSettings

    rs = ReceiptSettings.objects.filter(cafe=order.cafe).first()
    ctx = order_context(order, request=request)
    if rs and not rs.use_default and rs.template_html.strip():
        ctx["items_table"] = mark_safe(ctx["items_table"])
        ctx["logo"] = mark_safe(ctx["logo"])
        return Template(rs.template_html).render(Context(ctx))
    return render_to_string("receipts/default_receipt.html", ctx)


def _cafe_connection(cafe):
    """(connection, from_email) — the cafe's own SMTP, or the platform default."""
    from .models import ReceiptSettings

    rs = ReceiptSettings.objects.filter(cafe=cafe).first()
    if rs and not rs.smtp_use_default and rs.smtp_host:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=rs.smtp_host,
            port=rs.smtp_port or 587,
            username=rs.smtp_user,
            password=rs.smtp_password,
            use_tls=rs.smtp_use_tls,
        )
        from_email = rs.from_email or settings.DEFAULT_FROM_EMAIL
        return connection, from_email
    return get_connection(), settings.DEFAULT_FROM_EMAIL


def email_receipt(order, to_email, request=None):
    """Send the rendered receipt. Returns True on success; never raises to the caller."""
    if not to_email:
        return False
    try:
        html = render_receipt(order, request=request)
        connection, from_email = _cafe_connection(order.cafe)
        subject = f"Your receipt {order.order_number} — {order.cafe.name}"
        msg = EmailMultiAlternatives(
            subject, "Your receipt is below (view in an HTML email client).",
            from_email, [to_email], connection=connection,
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        return False


def email_feedback(order, to_email, request=None):
    if not to_email:
        return False
    from .models import ReceiptSettings
    rs = ReceiptSettings.objects.filter(cafe=order.cafe).first()
    ctx = order_context(order, request=request)
    
    html = ""
    if rs and rs.feedback_email_html.strip():
        html = Template(rs.feedback_email_html).render(Context(ctx))
    else:
        # Default fallback
        html = f'''
        <div style="font-family: sans-serif; max-width: 500px; margin: 0 auto; text-align: center;">
            <h2>Thank you for visiting {order.cafe.name}!</h2>
            <p>We hope you enjoyed your order (<b>#{order.order_number}</b>).</p>
            <p>Please take a moment to leave us a review. Your feedback helps us improve!</p>
            <a href="{ctx['review_url']}" style="display: inline-block; padding: 12px 24px; background: #c8903e; color: #fff; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 10px;">Leave a Review</a>
        </div>
        '''

    try:
        connection, from_email = _cafe_connection(order.cafe)
        subject = f"How was your experience at {order.cafe.name}?"
        msg = EmailMultiAlternatives(
            subject, "Please view this email in an HTML client to leave feedback.",
            from_email, [to_email], connection=connection,
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception:
        return False
