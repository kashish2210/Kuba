"""AI chatbot logic for per-cafe chat assistant (Gemini primary, Groq fallback)."""
import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are {bot_name}, a friendly AI assistant for {cafe_name}.

Your job is to help customers with questions about the menu, items, prices, and their dining experience.

RULES:
1. Only answer questions about {cafe_name}'s menu, food, and dining experience.
2. Be warm, concise, and helpful.
3. If asked something unrelated to the cafe or menu, politely redirect.
4. When recommending a product, ALWAYS include its ID in this exact format: [PRODUCT:id-here] so the frontend can render a clickable product card with its image.
5. Keep responses short (2-3 paragraphs max).
{custom_instructions}

Current menu:
{product_data}"""


def scrape_menu_data(cafe):
    """Build a menu JSON snapshot from the cafe's active products."""
    from .models import Product, ProductCategory

    categories_data = []
    for cat in ProductCategory.objects.filter(cafe=cafe).prefetch_related("products"):
        products = []
        for p in cat.products.filter(is_active=True):
            products.append({
                "id": p.id,
                "name": p.name,
                "price": float(p.price),
                "unit": p.unit_of_measure,
                "description": p.description or "",
                "tax_pct": float(p.tax_percentage),
                "is_featured": p.is_featured,
                "tags": [t.strip() for t in (p.tags or "").split(",") if t.strip()],
            })
        if products:
            categories_data.append({"category": cat.name, "items": products})

    return {"cafe": cafe.name, "menu": categories_data}


def _build_system_prompt(settings, cafe):
    product_data = settings.product_data_json or "{}"
    custom = settings.custom_instructions.strip()
    custom_block = f"\nExtra instructions:\n{custom}" if custom else ""
    return SYSTEM_PROMPT_TEMPLATE.format(
        bot_name=settings.bot_name,
        cafe_name=cafe.name,
        custom_instructions=custom_block,
        product_data=product_data,
    )


def _call_gemini(api_key, model, system_prompt, messages):
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = json.dumps({
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
    }).encode("utf-8")

    model_name = model or "gemini-1.5-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models"
        f"/{model_name}:generateContent?key={api_key}"
    )
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"Gemini HTTP {e.code}: {body[:500]}")
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise ValueError(f"Unexpected Gemini response: {json.dumps(data)[:300]}")


def _call_groq(api_key, model, system_prompt, messages):
    api_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    model_name = model or "llama-3.1-8b-instant"
    payload = json.dumps({
        "model": model_name,
        "messages": api_messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise ValueError(f"Unexpected Groq response: {json.dumps(data)[:300]}")


def get_ai_response(user_message, chat_history, assistant_settings, cafe):
    """
    Returns {'reply': str}.
    Tries Gemini first; falls back to Groq if Gemini fails or has no key.
    chat_history is a list of {'role': 'user'|'assistant', 'content': str}
    for all messages BEFORE the current user_message.
    """
    system_prompt = _build_system_prompt(assistant_settings, cafe)
    messages = list(chat_history[-20:])
    messages.append({"role": "user", "content": user_message})

    response_text = None

    if assistant_settings.gemini_api_key:
        try:
            response_text = _call_gemini(
                assistant_settings.gemini_api_key,
                assistant_settings.gemini_model,
                system_prompt,
                messages,
            )
            logger.info("Chatbot: Gemini responded")
        except Exception as exc:
            logger.warning("Chatbot: Gemini failed — %s", exc)

    if response_text is None and assistant_settings.groq_api_key:
        try:
            response_text = _call_groq(
                assistant_settings.groq_api_key,
                assistant_settings.groq_model,
                system_prompt,
                messages,
            )
            logger.info("Chatbot: Groq responded")
        except Exception as exc:
            logger.error("Chatbot: Groq also failed — %s", exc)

    if response_text is None:
        response_text = (
            "Sorry, I'm having trouble connecting right now. "
            "Please try again in a moment."
        )

    # Extract product references [PRODUCT:id] from the response
    import re
    product_ids = re.findall(r'\[PRODUCT:([\w-]+)\]', response_text)

    # Clean the [PRODUCT:id] tags from the visible text
    clean_text = re.sub(r'\[PRODUCT:[\w-]+\]', '', response_text).strip()

    # Fetch product data for the referenced products
    product_cards = []
    if product_ids:
        from .models import Product
        for pid in product_ids:
            try:
                p = Product.objects.get(id=pid, cafe=cafe, is_active=True)
                image_url = p.image.url if p.image else None
                product_cards.append({
                    'id': p.id,
                    'name': p.name,
                    'price': str(p.price),
                    'description': p.description,
                    'image': image_url,
                })
            except (Product.DoesNotExist, ValueError):
                pass

    return {
        "reply": clean_text,
        "products": product_cards
    }
