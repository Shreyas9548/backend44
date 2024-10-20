# Generated by Django 4.1 on 2024-09-06 15:22

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dynamic_entities", "0001_initial"),
        ("tenant", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="dynamicmodel",
            name="created_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name="dynamicmodel",
            name="tenant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="tenant.tenant",
            ),
        ),
        migrations.AddField(
            model_name="dynamicfield",
            name="dynamic_model",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="dynamic_entities.dynamicmodel",
            ),
        ),
    ]
