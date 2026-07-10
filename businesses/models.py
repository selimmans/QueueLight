import re

from django.core.exceptions import ValidationError
from django.db import models

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def _validate_e164(value):
    if value and not _E164_RE.match(value):
        raise ValidationError("Phone number must be in E.164 format (e.g. +15005550006).")


class Business(models.Model):
    MODE_BATCH = "batch"
    MODE_PERSON = "person"
    MODE_CHOICES = [(MODE_BATCH, "Batch"), (MODE_PERSON, "Person")]

    TYPE_RETAIL = "retail"
    TYPE_CLINIC = "clinic"
    TYPE_CHOICES = [(TYPE_RETAIL, "Retail"), (TYPE_CLINIC, "Clinic")]

    SMS_TEMPLATE_DEFAULT = "You're being called! Please proceed to {business_name}."
    PICKUP_NOTIFICATION_DEFAULT = "{business_name} — order #{order_number} is ready, come pick it up!"

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    business_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_RETAIL)
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    logo_colour = models.CharField(max_length=7, default="#3B82F6")
    colour_accent = models.CharField(max_length=7, default="#6366f1")
    colour_border = models.CharField(max_length=7, default="#e5e7eb")
    country = models.CharField(
        max_length=2,
        default="CA",
        help_text="ISO 3166-1 alpha-2 country code. Used to validate customer phone numbers on join.",
    )
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_PERSON)
    batch_size = models.PositiveIntegerField(default=5)
    twilio_from_number = models.CharField(
        max_length=20, blank=True, validators=[_validate_e164]
    )
    sms_template = models.CharField(
        max_length=320,
        default=SMS_TEMPLATE_DEFAULT,
        help_text="Placeholders: {business_name}, {customer_name}.",
    )
    menu_url = models.URLField(blank=True, default="")
    intake_fields = models.JSONField(default=list, blank=True)
    queue_enabled = models.BooleanField(default=True)
    pickup_enabled = models.BooleanField(default=False)
    pickup_show_wait_estimate = models.BooleanField(default=False)
    pickup_intake_fields = models.JSONField(default=list, blank=True)
    pickup_notification_message = models.CharField(
        max_length=320,
        blank=True,
        default="",
        help_text="Placeholders: {business_name}, {order_number}, {customer_name}. Leave blank to use default.",
    )
    POS_NONE = "none"
    POS_CLOVER = "clover"
    POS_SQUARE = "square"
    POS_TOAST = "toast"
    POS_LIGHTSPEED = "lightspeed"
    POS_CHOICES = [
        (POS_NONE, "None"),
        (POS_CLOVER, "Clover"),
        (POS_SQUARE, "Square"),
        (POS_TOAST, "Toast"),
        (POS_LIGHTSPEED, "Lightspeed"),
    ]

    IDENTIFIER_NAME = "name"
    IDENTIFIER_ORDER_NUMBER = "order_number"
    IDENTIFIER_PHONE = "phone"
    IDENTIFIER_CHOICES = [
        (IDENTIFIER_NAME, "Name"),
        (IDENTIFIER_ORDER_NUMBER, "Order number"),
        (IDENTIFIER_PHONE, "Phone number"),
    ]

    # ── Join page field configuration (pickup form) ─────────────────────
    # Name field
    field_name_enabled = models.BooleanField(
        default=True,
        help_text="Show the customer name field on the pickup join form.",
    )
    field_name_required = models.BooleanField(
        default=True,
        help_text="Require a name before the form can be submitted.",
    )
    # Order number field
    field_order_number_enabled = models.BooleanField(
        default=False,
        help_text="Show an order number field on the pickup join form.",
    )
    field_order_number_required = models.BooleanField(
        default=False,
        help_text="Require an order number before the form can be submitted.",
    )
    # Phone field — always shown, only required/optional is configurable
    field_phone_enabled = models.BooleanField(
        default=True,
        help_text="Phone number is always shown (needed for SMS notifications).",
    )
    field_phone_required = models.BooleanField(
        default=False,
        help_text="Require a phone number before the form can be submitted.",
    )

    pos_type = models.CharField(max_length=20, choices=POS_CHOICES, default=POS_NONE)
    # API token / access token for the connected POS system.
    # NOTE: stored plaintext — encryption at rest deferred (see KNOWN_ISSUES).
    pos_api_token = models.CharField(max_length=512, blank=True)
    # Clover: merchant ID.  Square: location ID.  Lightspeed: account ID.
    pos_merchant_id = models.CharField(max_length=255, blank=True)
    # Toast OAuth2 client credentials (client_id + client_secret).
    toast_client_id = models.CharField(max_length=255, blank=True)
    toast_client_secret = models.CharField(max_length=512, blank=True)

    # Which identifier the customer is asked for first on the pickup join page.
    default_identifier = models.CharField(
        max_length=20,
        choices=IDENTIFIER_CHOICES,
        default=IDENTIFIER_NAME,
        help_text="Primary field shown to customers when registering a pickup order.",
    )

    is_active = models.BooleanField(default=False)
    is_closing = models.BooleanField(default=False)
    avg_service_minutes = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # When set, pickup tag numbering ignores every PickupEntry registered before
    # this timestamp so the next order restarts at 001 without deleting history.
    pickup_tag_reset_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "businesses"

    def __str__(self):
        return self.name


class StaffPhone(models.Model):
    phone = models.CharField(max_length=20)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="staff_phones")
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = [("phone", "business")]

    def __str__(self):
        return f"{self.name} ({self.phone})"
