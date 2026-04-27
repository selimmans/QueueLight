from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0006_add_menu_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="colour_accent",
            field=models.CharField(default="#6366f1", max_length=7),
        ),
        migrations.AddField(
            model_name="business",
            name="colour_border",
            field=models.CharField(default="#e5e7eb", max_length=7),
        ),
    ]
