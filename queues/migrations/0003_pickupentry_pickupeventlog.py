import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0009_pickup_feature_fields"),
        ("queues", "0002_queueentry_intake_answers"),
    ]

    operations = [
        migrations.CreateModel(
            name="PickupEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pickup_entries",
                        to="businesses.business",
                    ),
                ),
                ("order_number", models.CharField(max_length=100)),
                ("customer_name", models.CharField(blank=True, max_length=255)),
                ("phone", models.CharField(blank=True, max_length=20)),
                (
                    "status",
                    models.CharField(
                        choices=[("waiting", "Waiting"), ("ready", "Ready"), ("picked_up", "Picked Up")],
                        default="waiting",
                        max_length=10,
                    ),
                ),
                ("registered_at", models.DateTimeField(auto_now_add=True)),
                ("ready_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name_plural": "pickup entries",
                "ordering": ["registered_at"],
            },
        ),
        migrations.CreateModel(
            name="PickupEventLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pickup_event_logs",
                        to="businesses.business",
                    ),
                ),
                (
                    "entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="event_logs",
                        to="queues.pickupentry",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("registered", "Registered"),
                            ("ready", "Ready"),
                            ("picked_up", "Picked Up"),
                            ("sms_sent", "SMS Sent"),
                            ("sms_failed", "SMS Failed"),
                        ],
                        max_length=20,
                    ),
                ),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("meta", models.JSONField(default=dict)),
            ],
            options={
                "ordering": ["timestamp"],
            },
        ),
    ]
