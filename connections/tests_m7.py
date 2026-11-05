"""Tahap M7: JSON aturan dari tombol Publish platform (topik rules/<id> dan tanda terimanya)."""
import importlib
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import ConnectionProfile, SubscriptionPreset
from .tests_session import sign_in

migration = importlib.import_module("connections.migrations.0004_rule_topic_subscription")
RULES = "{prefix}/{token}/rules/+"


class RuleTopicMigrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")
        cls.device = ConnectionProfile.objects.create(owner=cls.budi, name="Pump", host="iot.example.org",
                                                      platform_device_id=7)
        for position, topic in enumerate(["{prefix}/{token}/desired", "{prefix}/{token}/errors"]):
            SubscriptionPreset.objects.create(profile=cls.device, topic_filter=topic, position=position)
        cls.plain = ConnectionProfile.objects.create(owner=cls.budi, name="Lab", host="broker.example.org")

    def test_existing_device_profiles_get_rule_topic_once(self):
        migration.add_rule_topic(apps, None)
        migration.add_rule_topic(apps, None)                 # dijalankan ulang: tidak dobel
        rules = SubscriptionPreset.objects.filter(profile=self.device, topic_filter=RULES)
        self.assertEqual(rules.count(), 1)
        self.assertEqual((rules[0].qos, rules[0].color, rules[0].position), (1, "purple", 2))
        self.assertFalse(SubscriptionPreset.objects.filter(profile=self.plain).exists())

    def test_reverse_removes_it(self):
        migration.add_rule_topic(apps, None)
        migration.remove_rule_topic(apps, None)
        self.assertFalse(SubscriptionPreset.objects.filter(topic_filter=RULES).exists())
        self.assertEqual(self.device.subscriptions.count(), 2)


class RuleAckPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")
        cls.device = ConnectionProfile.objects.create(owner=cls.budi, name="Pump", host="iot.example.org",
                                                      platform_device_id=7)

    def test_session_page_has_rule_ack_option(self):
        sign_in(self.client, self.budi)
        response = self.client.get(reverse("connections:session", args=[self.device.pk]))
        self.assertContains(response, 'id="auto-rule-ack"')
        self.assertContains(response, "Acknowledge rule JSON automatically")
        # Template balasan (placeholder {{publish}} tidak dimakan template Django), tombol Reply now dan Reset.
        self.assertContains(response, '{"publish": {{publish}}, "ok": true, "size": {{size}}}')
        self.assertContains(response, 'id="rule-reply"')
        self.assertContains(response, 'id="rule-ack-reset"')

    def test_script_answers_rule_topic(self):
        script = (Path(settings.BASE_DIR) / "static" / "js" / "session.js").read_text()
        self.assertIn("function handleRule(topic, payload)", script)
        self.assertIn('deviceTopics.rule_ack.replace("{id}", rule.id)', script)
        self.assertIn('$("auto-rule-ack-template").value', script)
        # Pesan baru (Full/Compact): "publish" + "devices", device mengenali dirinya lewat MAC.
        self.assertIn('if (!Array.isArray(data.devices)) return \'missing "devices"\';', script)
        self.assertIn("rule.values.rule = text(data && data.name);", script)
        self.assertIn("if (handleRule(topic, payload)) return;", script)
