import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("deals", "0004_webhook_payload")]
    operations = [
        migrations.CreateModel(
            name="AgentProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("agent_type", models.CharField(choices=[("PROVIDER", "Provider"), ("BUYER", "Buyer")], max_length=12)),
                ("owner_name", models.CharField(max_length=120)),
                ("owner_email", models.EmailField(max_length=254)),
                ("description", models.TextField(blank=True, max_length=1000)),
                ("endpoint_url", models.URLField(blank=True, max_length=500)),
                ("protocol", models.CharField(default="DEALS", max_length=12)),
                ("capabilities", models.JSONField(blank=True, default=list)),
                ("services", models.JSONField(blank=True, default=list)),
                ("mandate", models.JSONField(blank=True, default=dict)),
                ("is_public", models.BooleanField(default=True)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("PAUSED", "Paused")], default="ACTIVE", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="AgentCredential",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("prefix", models.CharField(max_length=12, unique=True)),
                ("digest", models.CharField(max_length=64, unique=True)),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="credentials", to="deals.agentprofile")),
            ],
        ),
    ]
