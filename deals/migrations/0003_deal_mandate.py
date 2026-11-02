from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deals', '0002_ledger_append_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='deal',
            name='mandate',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
