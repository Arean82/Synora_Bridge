"""Add indexed, unique slug to Template with backfill for existing rows."""
import re

from django.db import migrations, models


def _slugify(name):
    base = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return base or "template"


def backfill_slugs(apps, schema_editor):
    Template = apps.get_model("configs", "Template")
    used = set()
    for tpl in Template.objects.order_by("id"):
        slug = _slugify(tpl.name)
        candidate = slug
        i = 2
        while candidate in used:
            candidate = f"{slug}_{i}"
            i += 1
        used.add(candidate)
        tpl.slug = candidate
        tpl.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("configs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="template",
            name="slug",
            field=models.SlugField(max_length=120, blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="template",
            name="slug",
            field=models.SlugField(max_length=120, unique=True, db_index=True, blank=True),
        ),
    ]
