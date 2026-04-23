from django.db import models


class Business(models.Model):
    MODE_BATCH = "batch"
    MODE_PERSON = "person"
    MODE_CHOICES = [(MODE_BATCH, "Batch"), (MODE_PERSON, "Person")]

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    logo_colour = models.CharField(max_length=7, default="#3B82F6")
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_PERSON)
    batch_size = models.PositiveIntegerField(default=5)
    twilio_from_number = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=False)
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
