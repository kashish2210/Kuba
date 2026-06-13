from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from cafe_pos.models import Order, OrderLineItem


KDS_ORDER_STATUSES = {
    Order.OrderStatus.SENT_TO_KITCHEN,
    Order.OrderStatus.PAID,
}


def kds_group_name(cafe_id):
    return f"kds_{cafe_id}"


def live_orders_group_name(cafe_id):
    return f"live_orders_{cafe_id}"


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


def order_display_payload(order):
    lines = list(order.line_items.select_related("product").order_by("id"))
    completed = sum(1 for line in lines if line.kds_status == OrderLineItem.KDSStatus.COMPLETED)
    total = len(lines)
    kitchen_names = sorted({
        line.prepared_by.get_username()
        for line in lines
        if line.prepared_by_id
    })
    if order.status == Order.OrderStatus.READY:
        display_status = "ready"
    elif order.status == Order.OrderStatus.PAID and total and completed == total:
        display_status = "ready"
    elif order.status == Order.OrderStatus.SENT_TO_KITCHEN:
        display_status = "preparing"
    elif order.status == Order.OrderStatus.PAID:
        display_status = "paid"
    else:
        display_status = order.status
    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "display_status": display_status,
        "table_number": order.table.table_number if order.table_id else None,
        "customer_name": order.customer.name if order.customer_id else "",
        "cashier_name": order.employee.get_username() if order.employee_id else "",
        "kitchen_staff": kitchen_names,
        "completed_lines": completed,
        "total_lines": total,
        "created_at": order.created_at.isoformat(),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
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


def current_display_orders(cafe):
    orders = (
        Order.objects.filter(
            cafe=cafe,
            status__in=[
                Order.OrderStatus.SENT_TO_KITCHEN,
                Order.OrderStatus.READY,
                Order.OrderStatus.PAID,
            ],
        )
        .select_related("table", "customer", "employee")
        .prefetch_related("line_items__product", "line_items__prepared_by")
        .order_by("-created_at")[:50]
    )
    return [order_display_payload(order) for order in orders]


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


def broadcast_order_status(order, event_type="order_status"):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        live_orders_group_name(order.cafe_id),
        {
            "type": "live.order",
            "event": event_type,
            "order": order_display_payload(order),
        },
    )
