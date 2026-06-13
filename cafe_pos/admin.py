import json

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import ChatAssistantSettings, ChatMessage, ChatSession, CustomReceiptTheme, ThemePurchase


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    fields = ("role", "content", "created_at")
    readonly_fields = ("role", "content", "created_at")
    extra = 0
    can_delete = True
    ordering = ("created_at",)
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "customer_email", "cafe", "order_link", "message_count", "terms_accepted", "created_at")
    list_filter = ("cafe", "terms_accepted", "created_at")
    search_fields = ("customer_name", "customer_email", "session_token")
    readonly_fields = ("cafe", "order", "session_token", "customer_name", "customer_email", "terms_accepted", "terms_accepted_at", "created_at")
    inlines = [ChatMessageInline]
    ordering = ("-created_at",)
    actions = ["delete_conversation_logs"]

    def has_add_permission(self, request):
        return False

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = "Messages"

    def order_link(self, obj):
        if obj.order_id:
            return format_html(
                '<a href="/admin/cafe_pos/order/{}/change/">{}</a>',
                obj.order_id, obj.order.order_number,
            )
        return "—"
    order_link.short_description = "Order"

    @admin.action(description="Delete selected conversation logs")
    def delete_conversation_logs(self, request, queryset):
        count = queryset.count()
        for session in queryset:
            session.messages.all().delete()
        self.message_user(request, f"Cleared messages from {count} session(s).")


@admin.register(ChatAssistantSettings)
class ChatAssistantSettingsAdmin(admin.ModelAdmin):
    list_display = ("cafe", "is_enabled", "bot_name", "gemini_model", "last_scraped_at")
    list_filter = ("is_enabled",)
    search_fields = ("cafe__name",)
    readonly_fields = ("last_scraped_at", "product_data_preview")
    actions = ["refresh_menu_data"]

    fieldsets = (
        ("Status", {"fields": ("cafe", "is_enabled", "bot_name", "welcome_message")}),
        ("AI Configuration", {
            "fields": ("gemini_api_key", "gemini_model", "groq_api_key", "groq_model"),
            "description": "Gemini is used first; Groq is the fallback if Gemini fails.",
        }),
        ("Menu Data", {
            "fields": ("last_scraped_at", "product_data_preview"),
            "description": "Use the 'Refresh menu data' action to update the menu snapshot fed to the AI.",
        }),
        ("Customisation", {"fields": ("custom_instructions", "terms_and_conditions")}),
    )

    def product_data_preview(self, obj):
        if not obj.product_data_json:
            return "No data yet. Run 'Refresh menu data'."
        try:
            parsed = json.loads(obj.product_data_json)
            cats = parsed.get("menu", [])
            total = sum(len(c.get("items", [])) for c in cats)
            return format_html(
                "<strong>{}</strong> categories, <strong>{}</strong> products",
                len(cats), total,
            )
        except Exception:
            return "Invalid JSON"
    product_data_preview.short_description = "Menu snapshot"

    @admin.action(description="Refresh menu data from current products")
    def refresh_menu_data(self, request, queryset):
        from .chatbot import scrape_menu_data
        updated = 0
        for obj in queryset:
            data = scrape_menu_data(obj.cafe)
            obj.product_data_json = json.dumps(data, ensure_ascii=False, indent=2)
            obj.last_scraped_at = timezone.now()
            obj.save(update_fields=["product_data_json", "last_scraped_at"])
            updated += 1
        self.message_user(request, f"Refreshed menu data for {updated} cafe(s).")


@admin.register(CustomReceiptTheme)
class CustomReceiptThemeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "price", "is_active", "total_sales", "total_revenue")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("total_sales", "total_revenue", "preview_theme")
    
    fieldsets = (
        ("Core Information", {
            "fields": ("name", "slug", "description", "price", "is_active"),
        }),
        ("Receipt Code & Visual Preview", {
            "fields": ("html_content", "preview_theme"),
            "description": "Enter valid receipt template HTML structure with styling and placeholders (like {{ name }}, {{ total }}).",
        }),
        ("Sales Metrics", {
            "fields": ("total_sales", "total_revenue"),
        }),
    )

    def total_sales(self, obj):
        if obj.pk:
            return obj.purchases.count()
        return 0
    total_sales.short_description = "Sales Count"

    def total_revenue(self, obj):
        if obj.pk:
            return f"${obj.purchases.count() * obj.price:.2f}"
        return "$0.00"
    total_revenue.short_description = "Total Revenue"

    def preview_theme(self, obj):
        if not obj.html_content:
            return "Enter HTML content and save to preview."
        return format_html(
            '<div style="border: 2px solid var(--primary, #c8903e); border-radius: 12px; overflow: hidden; max-width: 420px; background: #faf7f0; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">'
            '  <div style="background: #2c1e0f; color: #faf7f0; padding: 12px; font-weight: bold; font-size: 14px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.1);">'
            '    <span>Receipt Live Preview</span>'
            '    <span style="font-size: 11px; color: #c8903e; border: 1px solid #c8903e; padding: 2px 6px; border-radius: 4px;">{name}</span>'
            '  </div>'
            '  <iframe srcdoc="{html}" style="width: 100%; height: 450px; border: none; background: white;"></iframe>'
            '</div>',
            name=obj.name,
            html=obj.html_content
        )
    preview_theme.short_description = "Visual Preview"


@admin.register(ThemePurchase)
class ThemePurchaseAdmin(admin.ModelAdmin):
    list_display = ("cafe", "theme", "purchased_at", "purchase_price", "is_active")
    list_filter = ("is_active", "purchased_at", "theme")
    search_fields = ("cafe__name", "theme__name", "theme__slug")
    readonly_fields = ("purchase_price",)

    def purchase_price(self, obj):
        if obj.theme:
            return f"${obj.theme.price:.2f}"
        return "—"
    purchase_price.short_description = "Purchase Price"
