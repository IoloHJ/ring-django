from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ring_api", "0003_ringalert"),
    ]

    operations = [
        migrations.CreateModel(
            name="MobilePushDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("apns", "Apple Push Notification service"), ("adm", "Amazon Device Messaging")], max_length=10)),
                ("token", models.TextField(unique=True)),
                ("platform", models.CharField(blank=True, default="", max_length=20)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
