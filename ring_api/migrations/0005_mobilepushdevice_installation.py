from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("ring_api", "0004_mobilepushdevice"),
        ("security", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mobilepushdevice",
            name="installation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="push_devices",
                to="security.appinstallation",
            ),
        ),
    ]
