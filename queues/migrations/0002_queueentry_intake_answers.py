from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("queues", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="queueentry",
            name="intake_answers",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
