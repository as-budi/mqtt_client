"""Profil device IoT Platform yang sudah ada ikut subscribe JSON aturan (tahap M7)."""
from django.db import migrations
from django.db.models import Max

TOPIC = "{prefix}/{token}/rules/+"


def add_rule_topic(apps, schema_editor):
    ConnectionProfile = apps.get_model("connections", "ConnectionProfile")
    SubscriptionPreset = apps.get_model("connections", "SubscriptionPreset")
    for profile in ConnectionProfile.objects.filter(platform_device_id__isnull=False):
        presets = SubscriptionPreset.objects.filter(profile=profile)
        if presets.filter(topic_filter=TOPIC).exists():
            continue
        position = (presets.aggregate(n=Max("position"))["n"] or 0) + 1
        SubscriptionPreset.objects.create(profile=profile, topic_filter=TOPIC, qos=1, color="purple",
                                          position=position)


def remove_rule_topic(apps, schema_editor):
    SubscriptionPreset = apps.get_model("connections", "SubscriptionPreset")
    SubscriptionPreset.objects.filter(profile__platform_device_id__isnull=False, topic_filter=TOPIC).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("connections", "0003_connectionprofile_ca_pem_and_more"),
    ]

    operations = [
        migrations.RunPython(add_rule_topic, remove_rule_topic),
    ]
