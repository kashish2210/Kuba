import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        CASHIER = "cashier", "Cashier"
        KITCHEN = "kitchen", "Kitchen Display"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    cafe = models.ForeignKey(
        "tenants.Cafe",
        on_delete=models.CASCADE,
        related_name="profiles",
        null=True,
        blank=True,
        help_text="The cafe this member belongs to. Null for platform staff.",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CASHIER)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class ProductCategory(models.Model):
    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="product_categories")
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cafe", "name"], name="uniq_category_per_cafe"),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    class UnitOfMeasure(models.TextChoices):
        PER_PIECE = "per piece", "Per piece"
        PER_CUP = "per cup", "Per cup"
        PER_GLASS = "per glass", "Per glass"
        PER_PLATE = "per plate", "Per plate"
        PER_BOWL = "per bowl", "Per bowl"
        PER_SLICE = "per slice", "Per slice"
        PER_SERVING = "per serving", "Per serving"
        PER_PACKET = "per packet", "Per packet"
        PER_BOTTLE = "per bottle", "Per bottle"
        PER_KILOGRAM = "per kilogram", "Per kilogram"
        PER_GRAM = "per gram", "Per gram"
        PER_LITRE = "per litre", "Per litre"
        PER_MILLILITRE = "per millilitre", "Per millilitre"

    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=200)
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name="products")
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    unit_of_measure = models.CharField(max_length=20, choices=UnitOfMeasure.choices)
    tax_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to="product_images/", null=True, blank=True)
    show_in_kds = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    # New fields for features and upselling
    is_featured = models.BooleanField(default=False, help_text="Mark as Featured or Chef's Special")
    tags = models.CharField(max_length=255, null=True, blank=True, help_text="Comma-separated tags (e.g. Spicy, Vegan, Bestseller)")
    cross_sells = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="recommended_with")

    def __str__(self):
        return self.name


class Floor(models.Model):
    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="floors")
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0, help_text="Lower number appears first.")
    canvas_mode = models.BooleanField(default=False, help_text="If true, displays tables on an interactive grid canvas instead of a list.")

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class CafeTable(models.Model):
    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="tables")
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name="tables")
    table_number = models.CharField(max_length=20)
    sort_order = models.PositiveIntegerField(default=0, help_text="Order within the floor.")
    seats = models.PositiveIntegerField(validators=[MinValueValidator(1)], default=4)
    is_active = models.BooleanField(default=True)
    is_occupied = models.BooleanField(default=False, help_text="Locked by staff until table is manually cleared.")
    
    # Spatial fields for canvas mode
    pos_x = models.FloatField(default=0.0)
    pos_y = models.FloatField(default=0.0)
    width = models.FloatField(default=100.0)
    height = models.FloatField(default=100.0)
    shape = models.CharField(max_length=20, default="rect", choices=[("rect", "Rectangle"), ("circle", "Circle")])

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["floor", "table_number"], name="uniq_table_per_floor"),
        ]

    def __str__(self):
        return f"{self.floor.name} - {self.table_number}"


class PaymentMethod(models.Model):
    class MethodType(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        UPI = "upi", "UPI"

    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="payment_methods")
    type = models.CharField(max_length=10, choices=MethodType.choices)
    is_enabled = models.BooleanField(default=False)
    upi_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cafe", "type"], name="uniq_payment_method_per_cafe"),
        ]

    def __str__(self):
        return self.get_type_display()


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed"

    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="coupons")
    name = models.CharField(max_length=150, blank=True)
    code = models.CharField(max_length=50)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cafe", "code"], name="uniq_coupon_code_per_cafe"),
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code


class Promotion(models.Model):
    class ApplyTo(models.TextChoices):
        PRODUCT = "product", "Product"
        ORDER = "order", "Order"

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed"

    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="promotions")
    name = models.CharField(max_length=150)
    apply_to = models.CharField(max_length=20, choices=ApplyTo.choices)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="promotions",
        null=True,
        blank=True,
    )
    min_quantity = models.PositiveIntegerField(null=True, blank=True)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(apply_to="product", product__isnull=False, min_quantity__isnull=False)
                    | Q(apply_to="order", min_order_amount__isnull=False)
                ),
                name="promotion_apply_to_required_fields",
            ),
        ]

    def __str__(self):
        return self.name


class LoyaltySettings(models.Model):
    cafe = models.OneToOneField("tenants.Cafe", on_delete=models.CASCADE, related_name="loyalty_settings")
    level_1_orders = models.PositiveIntegerField(default=1)
    level_2_orders = models.PositiveIntegerField(default=3)
    level_3_orders = models.PositiveIntegerField(default=10)
    level_4_orders = models.PositiveIntegerField(default=20)
    level_5_orders = models.PositiveIntegerField(default=50)
    points_per_order = models.PositiveIntegerField(default=10)

    class Meta:
        verbose_name = "Loyalty settings"
        verbose_name_plural = "Loyalty settings"

    def thresholds(self):
        return [
            self.level_1_orders,
            self.level_2_orders,
            self.level_3_orders,
            self.level_4_orders,
            self.level_5_orders,
        ]

    def level_for_orders(self, order_count):
        level = 0
        for index, threshold in enumerate(self.thresholds(), start=1):
            if order_count >= threshold:
                level = index
        return level

    def __str__(self):
        return f"Loyalty settings — {self.cafe.name}"


class Customer(models.Model):
    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=150)
    email = models.EmailField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    manual_loyalty_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Optional admin override for this customer's loyalty level.",
    )
    is_banned = models.BooleanField(default=False)
    ban_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cafe", "email"],
                name="uniq_customer_email_per_cafe",
                condition=Q(email__isnull=False),
            ),
        ]

    def __str__(self):
        return self.name

    def paid_order_count(self):
        return self.orders.filter(status=Order.OrderStatus.PAID).count()

    def loyalty_snapshot(self, settings_obj=None, paid_orders=None):
        if settings_obj is None:
            settings_obj, _ = LoyaltySettings.objects.get_or_create(cafe=self.cafe)
        if paid_orders is None:
            paid_orders = self.paid_order_count()
        computed_level = settings_obj.level_for_orders(paid_orders)
        level = self.manual_loyalty_level or computed_level
        return {
            "paid_orders": paid_orders,
            "level": level,
            "computed_level": computed_level,
            "manual_level": self.manual_loyalty_level,
            "points": paid_orders * settings_obj.points_per_order,
            "next_level_orders": next(
                (threshold for threshold in settings_obj.thresholds() if paid_orders < threshold),
                None,
            ),
        }


class POSSession(models.Model):
    class SessionStatus(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="pos_sessions")
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="opened_sessions")
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    closing_sale_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=SessionStatus.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cafe"],
                condition=Q(status="open"),
                name="unique_open_session_per_cafe",
            ),
        ]

    def __str__(self):
        return f"Session {self.id} ({self.status})"


class Order(models.Model):
    class OrderStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT_TO_KITCHEN = "sent_to_kitchen", "Sent to Kitchen"
        READY = "ready", "Ready"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="orders")
    order_number = models.CharField(max_length=30)
    session = models.ForeignKey(POSSession, on_delete=models.PROTECT, related_name="orders")
    table = models.ForeignKey(CafeTable, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=OrderStatus.choices)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    promotion = models.ForeignKey(Promotion, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    review_token = models.UUIDField(default=uuid.uuid4, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cafe", "order_number"], name="uniq_order_number_per_cafe"),
        ]

    def __str__(self):
        return self.order_number


class OrderLineItem(models.Model):
    class KDSStatus(models.TextChoices):
        TO_COOK = "to_cook", "To Cook"
        PREPARING = "preparing", "Preparing"
        COMPLETED = "completed", "Completed"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="line_items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_lines")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    line_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    line_total = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    kds_status = models.CharField(max_length=20, choices=KDSStatus.choices, default=KDSStatus.TO_COOK)
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_order_lines",
    )

    def __str__(self):
        return f"{self.order.order_number} - {self.product.name}"


class PaymentRecord(models.Model):
    class MethodType(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        UPI = "upi", "UPI"
        RAZORPAY = "razorpay", "Razorpay"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment_record")
    method_type = models.CharField(max_length=10, choices=MethodType.choices)
    amount_tendered = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    change_due = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    transaction_ref = models.CharField(max_length=100, null=True, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Payment for {self.order.order_number}"


class OrderReview(models.Model):
    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="order_reviews")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_reviews_as_cashier",
    )
    kitchen_staff = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="order_reviews_as_kitchen",
    )
    rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    customer_name = models.CharField(max_length=150, blank=True)
    customer_email = models.EmailField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.order_number} — {self.rating}/5"


class PaymentSettings(models.Model):
    """Per-cafe payment gateway configuration (Razorpay / Stripe / UPI)."""

    cafe = models.OneToOneField("tenants.Cafe", on_delete=models.CASCADE, related_name="payment_settings")

    upi_id = models.CharField(max_length=100, blank=True, help_text="UPI VPA used for the POS QR, e.g. cafe@ybl")
    upi_payee_name = models.CharField(max_length=100, blank=True, help_text="Name shown in the UPI app.")

    razorpay_enabled = models.BooleanField(default=False)
    razorpay_key_id = models.CharField(max_length=120, blank=True)
    razorpay_key_secret = models.CharField(max_length=120, blank=True)

    stripe_enabled = models.BooleanField(default=False)
    stripe_publishable_key = models.CharField(max_length=160, blank=True)
    stripe_secret_key = models.CharField(max_length=160, blank=True)

    class Meta:
        verbose_name = "Payment settings"
        verbose_name_plural = "Payment settings"

    def __str__(self):
        return f"Payment settings — {self.cafe.name}"


class FeedbackQuestion(models.Model):
    QUESTION_TYPES = (
        ("rating", "Star Rating (1-5)"),
        ("text", "Text Input"),
    )
    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="feedback_questions")
    question_text = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.question_text} ({self.type})"


class FeedbackResponse(models.Model):
    review = models.ForeignKey(OrderReview, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(FeedbackQuestion, on_delete=models.CASCADE)
    rating_value = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    text_value = models.TextField(blank=True)

    def __str__(self):
        return f"Response to {self.question.question_text}"


class ChatAssistantSettings(models.Model):
    """Per-cafe AI chat assistant configuration."""

    cafe = models.OneToOneField("tenants.Cafe", on_delete=models.CASCADE, related_name="chat_assistant_settings")
    is_enabled = models.BooleanField(default=False)
    bot_name = models.CharField(max_length=100, default="Assistant")
    welcome_message = models.TextField(
        blank=True,
        default="Hi! I'm your assistant. Ask me anything about our menu.",
    )
    custom_instructions = models.TextField(blank=True, help_text="Extra instructions for the AI (e.g. tone, topics to avoid).")
    gemini_api_key = models.CharField(max_length=200, blank=True)
    gemini_model = models.CharField(max_length=100, default="gemini-2.5-flash")
    groq_api_key = models.CharField(max_length=200, blank=True)
    groq_model = models.CharField(max_length=100, default="llama-3.1-8b-instant")
    product_data_json = models.TextField(blank=True, help_text="Auto-generated menu snapshot fed to the AI.")
    last_scraped_at = models.DateTimeField(null=True, blank=True)
    terms_and_conditions = models.TextField(
        blank=True,
        help_text="Terms customers must accept before chatting. Leave blank to skip the T&C step.",
    )

    class Meta:
        verbose_name = "Chat assistant settings"
        verbose_name_plural = "Chat assistant settings"

    def __str__(self):
        return f"Chat assistant — {self.cafe.name}"


class ChatSession(models.Model):
    """A public chat session created when an order is paid and emailed to the customer."""

    cafe = models.ForeignKey("tenants.Cafe", on_delete=models.CASCADE, related_name="chat_sessions")
    order = models.ForeignKey(
        "Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="chat_sessions",
    )
    session_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer_name = models.CharField(max_length=150, blank=True)
    customer_email = models.EmailField(max_length=255, blank=True)
    terms_accepted = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        label = self.customer_name or self.customer_email or str(self.session_token)[:8]
        return f"Chat {label}"

    def message_count(self):
        return self.messages.count()


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"


class ReceiptSettings(models.Model):
    """Per-cafe receipt template + SMTP (falls back to the platform default)."""

    cafe = models.OneToOneField("tenants.Cafe", on_delete=models.CASCADE, related_name="receipt_settings")
    use_default = models.BooleanField(default=True, help_text="Use the built-in receipt design.")
    template_html = models.TextField(blank=True, help_text="Custom receipt HTML with {{ data pills }}.")
    feedback_email_html = models.TextField(blank=True, help_text="Custom feedback email HTML.")

    smtp_use_default = models.BooleanField(default=True, help_text="Send via the platform's default email.")
    smtp_host = models.CharField(max_length=120, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_user = models.CharField(max_length=160, blank=True)
    smtp_password = models.CharField(max_length=200, blank=True)
    smtp_use_tls = models.BooleanField(default=True)
    from_email = models.CharField(max_length=200, blank=True, help_text="e.g. Cafe <orders@cafe.com>")

    class Meta:
        verbose_name = "Receipt settings"
        verbose_name_plural = "Receipt settings"

    def __str__(self):
        return f"Receipt settings — {self.cafe.name}"
