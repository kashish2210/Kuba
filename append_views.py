import sys

with open('dashboard/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

placeholder = '# ─────────────────────────────────────────────────────────────────────────────\n# Placeholders for deferred POS modules'

views_code = """
@cafe_admin_required
def feedback_settings(request):
    cafe = request.cafe
    receipt_settings, _ = ReceiptSettings.objects.get_or_create(cafe=cafe)
    
    if request.method == "POST":
        receipt_settings.feedback_email_html = request.POST.get("feedback_email_html", "")
        receipt_settings.save(update_fields=["feedback_email_html"])
        
        # Handle dynamic questions
        q_ids = request.POST.getlist("question_id")
        q_texts = request.POST.getlist("question_text")
        q_types = request.POST.getlist("question_type")
        
        # Delete existing ones not in the submitted list
        existing_ids = [int(i) for i in q_ids if i.isdigit()]
        FeedbackQuestion.objects.filter(cafe=cafe).exclude(id__in=existing_ids).delete()
        
        for idx, text in enumerate(q_texts):
            text = text.strip()
            if not text:
                continue
            qid = q_ids[idx] if idx < len(q_ids) else ""
            qtype = q_types[idx] if idx < len(q_types) else "rating"
            
            if qid.isdigit():
                q = FeedbackQuestion.objects.get(id=int(qid), cafe=cafe)
                q.question_text = text
                q.type = qtype
                q.sort_order = idx
                q.save()
            else:
                FeedbackQuestion.objects.create(
                    cafe=cafe, question_text=text, type=qtype, sort_order=idx
                )
                
        messages.success(request, "Feedback settings updated successfully.")
        return redirect("dashboard:feedback-settings")
        
    questions = FeedbackQuestion.objects.filter(cafe=cafe).order_by("sort_order")
    
    return render(request, "dashboard/feedback_settings.html", {
        "receipt_settings": receipt_settings,
        "questions": questions,
    })

@cafe_admin_required
def feedback_report(request):
    cafe = request.cafe
    reviews = OrderReview.objects.filter(cafe=cafe).select_related("order", "customer", "cashier").prefetch_related("responses__question", "kitchen_staff").order_by("-created_at")
    
    paginator = Paginator(reviews, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    return render(request, "dashboard/feedback_report.html", {
        "page_obj": page_obj,
    })
"""

if placeholder in content:
    content = content.replace(placeholder, views_code + '\n' + placeholder)
    with open('dashboard/views.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Views appended successfully.')
else:
    print('Placeholder not found.')
