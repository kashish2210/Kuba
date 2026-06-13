from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from cafe_pos.models import Order, OrderLineItem


KDS_ORDER_STATUSES = {
    Order.OrderStatus.SENT_TO_KITCHEN,
    Order.OrderStatus.PAID,
}


def kds_group_name(cafe_id):
    return f"kds_{cafe_id}"


def order_ticket(order):
    lines = []
    for line in order.line_items.select_related("product", "product__category").order_by("id"):
        if not line.product.show_in_kds:
            continue
        lines.append({
            "id": line.id,
            "product_id": line.product_id,
            "product_name": line.product.name,
            "category_id": line.product.category_id,
            "category_name": line.product.category.name,
            "quantity": line.quantity,
            "kds_status": line.kds_status,
        })

    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "table_number": order.table.table_number if order.table_id else None,
        "created_at": order.created_at.isoformat(),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "lines": lines,
    }


def current_kds_tickets(cafe):
    orders = (
        Order.objects.filter(cafe=cafe, status__in=KDS_ORDER_STATUSES)
        .select_related("table")
        .prefetch_related("line_items__product__category")
        .order_by("created_at")
    )
    tickets = []
    for order in orders:
        ticket = order_ticket(order)
        if not ticket["lines"]:
            continue
        if all(line["kds_status"] == OrderLineItem.KDSStatus.COMPLETED for line in ticket["lines"]):
            continue
        tickets.append(ticket)
    return tickets


def broadcast_order_to_kds(order, event_type="order_updated"):
    ticket = order_ticket(order)
    if not ticket["lines"]:
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        kds_group_name(order.cafe_id),
        {
            "type": "kds.order",
            "event": event_type,
            "order": ticket,
        },
    )
