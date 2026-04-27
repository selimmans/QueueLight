from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0007_business_colour_accent_colour_border"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="business_type",
            field=models.CharField(
                choices=[("retail", "Retail"), ("clinic", "Clinic")],
                default="retail",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="business",
            name="intake_fields",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
