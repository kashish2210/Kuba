"""Public chat session views — no login required, token-gated."""
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import ChatAssistantSettings, ChatMessage, ChatSession

MAX_MESSAGES_PER_SESSION = 100


@ensure_csrf_cookie
def chat_session(request, token):
    session = get_object_or_404(ChatSession, session_token=token, cafe=request.cafe)
    assistant = ChatAssistantSettings.objects.filter(cafe=request.cafe).first()

    if not assistant or not assistant.is_enabled:
        return render(request, "chatbot/unavailable.html", {"cafe": request.cafe})

    messages = session.messages.order_by("created_at")
    needs_terms = bool(assistant.terms_and_conditions.strip()) and not session.terms_accepted
    return render(request, "chatbot/session.html", {
        "session": session,
        "assistant": assistant,
        "messages": messages,
        "cafe": request.cafe,
        "needs_terms": needs_terms,
    })


@require_POST
def accept_terms(request, token):
    session = get_object_or_404(ChatSession, session_token=token, cafe=request.cafe)
    session.terms_accepted = True
    session.terms_accepted_at = timezone.now()
    session.save(update_fields=["terms_accepted", "terms_accepted_at"])
    return JsonResponse({"ok": True})


@require_POST
def chat_message(request, token):
    session = get_object_or_404(ChatSession, session_token=token, cafe=request.cafe)
    assistant = ChatAssistantSettings.objects.filter(cafe=request.cafe).first()

    if not assistant or not assistant.is_enabled:
        return JsonResponse({"error": "Chat assistant is not available."}, status=403)

    if bool(assistant.terms_and_conditions.strip()) and not session.terms_accepted:
        return JsonResponse({"error": "Please accept the terms and conditions first."}, status=400)

    try:
        data = json.loads(request.body)
        user_message = (data.get("message") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        user_message = (request.POST.get("message") or "").strip()

    if not user_message:
        return JsonResponse({"error": "Message cannot be empty."}, status=400)

    existing_count = session.messages.count()
    if existing_count >= MAX_MESSAGES_PER_SESSION:
        return JsonResponse({"error": "Message limit reached for this session."}, status=429)

    # Capture history BEFORE saving the new user message
    history = list(session.messages.order_by("created_at").values("role", "content"))

    ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=user_message)

    from .chatbot import get_ai_response
    result = get_ai_response(user_message, history, assistant, request.cafe)

    ChatMessage.objects.create(
        session=session, role=ChatMessage.Role.ASSISTANT, content=result["reply"]
    )

    return JsonResponse({"reply": result["reply"], "products": result.get("products", [])})
