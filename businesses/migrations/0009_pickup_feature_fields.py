from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0008_business_type_intake_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="queue_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="business",
            name="pickup_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="business",
            name="pickup_notification_message",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Placeholders: {business_name}, {order_number}, {customer_name}. Leave blank to use default.",
                max_length=320,
            ),
        ),
    ]
