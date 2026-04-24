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

    SMS_TEMPLATE_DEFAULT = "You're being called! Please proceed to {business_name}."

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    logo_colour = models.CharField(max_length=7, default="#3B82F6")
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
    is_active = models.BooleanField(default=False)
    avg_service_minutes = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
