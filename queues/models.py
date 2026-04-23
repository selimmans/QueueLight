from django.db import models

from businesses.models import Business


class QueueEntry(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        CALLED = "called", "Called"
        COMPLETED = "completed", "Completed"
        ABANDONED = "abandoned", "Abandoned"
        SKIPPED = "skipped", "Skipped"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="queue_entries")
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    position = models.PositiveIntegerField()
    batch_number = models.PositiveIntegerField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    called_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]
        verbose_name_plural = "queue entries"

    def __str__(self):
        return f"{self.name} — {self.business.slug} #{self.position} ({self.status})"


class QueueEventLog(models.Model):
    class EventType(models.TextChoices):
        JOINED = "joined", "Joined"
        CALLED = "called", "Called"
        SKIPPED = "skipped", "Skipped"
        ABANDONED = "abandoned", "Abandoned"
        SMS_SENT = "sms_sent", "SMS Sent"
        SMS_FAILED = "sms_failed", "SMS Failed"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="event_logs")
    entry = models.ForeignKey(
        QueueEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name="event_logs"
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    before_values = models.JSONField(default=dict)
    after_values = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.event_type} — {self.business.slug} @ {self.timestamp}"
