import sys
with open('dashboard/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

placeholder = '# ─────────────────────────────────────────────────────────────────────────────\n# Placeholders for deferred POS modules'

preview_code = """
@cafe_admin_required
@require_POST
def feedback_preview(request):
    from cafe_pos.receipts import order_context
    from django.template import Context, Template
    from django.template.loader import render_to_string
    from django.utils.safestring import mark_safe
    
    order = Order.objects.filter(cafe=request.cafe).order_by("-created_at").first()
    if order is None:
        return HttpResponse("<p style='padding:24px;font-family:sans-serif;color:#888'>No orders yet — take one in the POS to preview.</p>")
        
    html_template = (request.POST.get("feedback_email_html") or "").strip()
    ctx = order_context(order)
    ctx["items_table"] = mark_safe(ctx.get("items_table", ""))
    ctx["logo"] = mark_safe(ctx.get("logo", ""))
    
    if not html_template:
        html = f'''
        <div style="font-family: sans-serif; max-width: 500px; margin: 0 auto; text-align: center;">
            <h2>Thank you for visiting {order.cafe.name}!</h2>
            <p>We hope you enjoyed your order (<b>#{order.order_number}</b>).</p>
            <p>Please take a moment to leave us a review. Your feedback helps us improve!</p>
            <a href="{ctx.get('review_url', '#')}" style="display: inline-block; padding: 12px 24px; background: #c8903e; color: #fff; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 10px;">Leave a Review</a>
        </div>
        '''
        return HttpResponse(html)
        
    try:
        html = Template(html_template).render(Context(ctx))
    except Exception as exc:
        html = f"<p style='color:#c0392b;padding:24px;font-family:sans-serif'>Template error: {exc}</p>"
    return HttpResponse(html)
"""

content = content.replace(placeholder, preview_code + '\n' + placeholder)
with open('dashboard/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Feedback preview appended')
