from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deals', '0003_deal_mandate'),
    ]

    operations = [
        migrations.AddField(
            model_name='webhookevent',
            name='payload',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
