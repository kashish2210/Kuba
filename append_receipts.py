import sys

with open('cafe_pos/receipts.py', 'r', encoding='utf-8') as f:
    content = f.read()

append_code = """
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
"""

content += '\n' + append_code
with open('cafe_pos/receipts.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Receipt appended successfully.')
