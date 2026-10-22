"""Tes profil koneksi (tahap M2)."""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .models import ConnectionProfile, SubscriptionPreset
from .validators import validate_topic_filter, validate_topic_name


class TopicValidatorTests(SimpleTestCase):
    def test_topic_filters(self):
        for good in ["iot/abc/telemetry", "iot/+/status", "#", "+/+/errors", "iot/#", "$share/g/iot/+", "a//b"]:
            validate_topic_filter(good)
        for bad in ["", "iot/#/x", "iot/a+", "iot/ab#", "a\x00b"]:
            with self.assertRaises(ValidationError, msg=bad):
                validate_topic_filter(bad)

    def test_topic_names(self):
        validate_topic_name("iot/abc/status")
        for bad in ["", "iot/+/x", "iot/#"]:
            with self.assertRaises(ValidationError, msg=bad):
                validate_topic_name(bad)


def form_data(**overrides):
    data = {
        "name": "Lab broker", "color": "blue", "scheme": "wss", "host": "broker.emqx.io", "port": "8084",
        "path": "mqtt", "client_id_prefix": "mqttc-", "username": "", "protocol_version": "4", "keepalive": "60",
        "clean_start": "on", "will_topic": "", "will_payload": "", "will_qos": "0",
        "subscriptions-TOTAL_FORMS": "0", "subscriptions-INITIAL_FORMS": "0",
        "subscriptions-MIN_NUM_FORMS": "0", "subscriptions-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


def with_subscriptions(data, *rows):
    data["subscriptions-TOTAL_FORMS"] = str(len(rows))
    for index, (topic, qos) in enumerate(rows):
        data[f"subscriptions-{index}-topic_filter"] = topic
        data[f"subscriptions-{index}-qos"] = str(qos)
        data[f"subscriptions-{index}-color"] = "gray"
    return data


class ProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi")
        cls.siti = User.objects.create(username="siti")
        cls.siti_profile = ConnectionProfile.objects.create(owner=cls.siti, name="Siti broker", host="example.org")

    def setUp(self):
        self.client.force_login(self.budi)

    def test_create_with_subscriptions(self):
        data = with_subscriptions(form_data(), ("iot/+/telemetry", 1), ("iot/#", 0))
        response = self.client.post(reverse("connections:create"), data)
        self.assertRedirects(response, reverse("connections:list"))
        profile = ConnectionProfile.objects.get(owner=self.budi)
        self.assertEqual(profile.url, "wss://broker.emqx.io:8084/mqtt")      # "/" ditambahkan di depan path
        self.assertEqual(profile.route, "direct")
        self.assertEqual([s.topic_filter for s in profile.subscriptions.all()], ["iot/+/telemetry", "iot/#"])

    def test_default_port_and_tcp_scheme(self):
        self.client.post(reverse("connections:create"), form_data(scheme="mqtts", port="", path="/mqtt"))
        profile = ConnectionProfile.objects.get(owner=self.budi)
        self.assertEqual((profile.url, profile.path, profile.route), ("mqtts://broker.emqx.io:8883", "", "relay"))

    def test_validation_errors(self):
        cases = [
            ({"host": "wss://broker.emqx.io"}, "host", "without wss://"),
            ({"host": "bad host"}, "host", "not a valid host"),
            ({"port": "70000"}, "port", "1 to 65535"),
            ({"will_payload": "bye"}, "will_topic", "Enter the topic"),
            ({"will_topic": "iot/+/status"}, "will_topic", "wildcards"),
        ]
        for overrides, field, text in cases:
            response = self.client.post(reverse("connections:create"), form_data(**overrides))
            self.assertEqual(response.status_code, 200, overrides)
            self.assertIn(text, " ".join(response.context["form"].errors[field]), overrides)
        self.assertFalse(ConnectionProfile.objects.filter(owner=self.budi).exists())

    def test_name_unique_per_owner_only(self):
        self.client.post(reverse("connections:create"), form_data(name="Siti broker"))     # nama sama milik siti: boleh
        response = self.client.post(reverse("connections:create"), form_data(name="siti BROKER"))
        self.assertIn("already have", str(response.context["form"].errors["name"]))

    @override_settings(DEBUG=False)
    def test_plain_ws_is_refused_on_the_server(self):
        response = self.client.post(reverse("connections:create"), form_data(scheme="ws", port="8083"))
        self.assertIn("Browsers block ws://", str(response.context["form"].errors["scheme"]))

    def test_bad_and_duplicate_subscriptions(self):
        data = with_subscriptions(form_data(), ("iot/#/x", 0), ("a/b", 0), ("a/b", 1))
        response = self.client.post(reverse("connections:create"), data)
        self.assertEqual(response.status_code, 200)
        errors = [form.errors.get("topic_filter") for form in response.context["formset"].forms]
        self.assertIn("must be a whole level", str(errors[0]))
        self.assertIn("duplicate", str(response.context["formset"].non_form_errors()))

    def test_preset(self):
        response = self.client.get(reverse("connections:create"), {"preset": "hivemq"})
        form = response.context["form"]
        self.assertEqual((form.initial["host"], form.initial["port"]), ("broker.hivemq.com", 8884))
        self.assertContains(response, "HiveMQ public broker")

    def test_list_shows_only_own_profiles(self):
        ConnectionProfile.objects.create(owner=self.budi, name="Mine", host="broker.emqx.io", port=8084)
        response = self.client.get(reverse("connections:list"))
        self.assertContains(response, "Mine")
        self.assertContains(response, "wss://broker.emqx.io:8084/mqtt")
        self.assertNotContains(response, "Siti broker")

    def test_other_users_profile_is_404(self):
        pk = self.siti_profile.pk
        self.assertEqual(self.client.get(reverse("connections:edit", args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("connections:delete", args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("connections:duplicate", args=[pk])).status_code, 404)
        self.assertTrue(ConnectionProfile.objects.filter(pk=pk).exists())

    def test_edit_replaces_subscriptions(self):
        profile = ConnectionProfile.objects.create(owner=self.budi, name="Edit me", host="broker.emqx.io")
        sub = SubscriptionPreset.objects.create(profile=profile, topic_filter="old/#")
        data = form_data(name="Edited", host="broker.emqx.io", **{
            "subscriptions-TOTAL_FORMS": "2", "subscriptions-INITIAL_FORMS": "1",
            "subscriptions-0-id": str(sub.pk), "subscriptions-0-profile": str(profile.pk),
            "subscriptions-0-topic_filter": "old/#", "subscriptions-0-qos": "0", "subscriptions-0-color": "gray",
            "subscriptions-0-DELETE": "on",
            "subscriptions-1-topic_filter": "new/+", "subscriptions-1-qos": "2", "subscriptions-1-color": "red",
        })
        response = self.client.post(reverse("connections:edit", args=[profile.pk]), data)
        self.assertRedirects(response, reverse("connections:list"))
        profile.refresh_from_db()
        self.assertEqual(profile.name, "Edited")
        self.assertEqual([(s.topic_filter, s.qos) for s in profile.subscriptions.all()], [("new/+", 2)])

    def test_duplicate_copies_subscriptions(self):
        profile = ConnectionProfile.objects.create(owner=self.budi, name="Lab", host="broker.emqx.io")
        SubscriptionPreset.objects.create(profile=profile, topic_filter="lab/#")
        self.client.post(reverse("connections:duplicate", args=[profile.pk]))
        self.client.post(reverse("connections:duplicate", args=[profile.pk]))
        names = sorted(ConnectionProfile.objects.filter(owner=self.budi).values_list("name", flat=True))
        self.assertEqual(names, ["Lab", "Lab (copy 2)", "Lab (copy)"])
        copy = ConnectionProfile.objects.get(owner=self.budi, name="Lab (copy)")
        self.assertEqual([s.topic_filter for s in copy.subscriptions.all()], ["lab/#"])
        self.assertEqual(SubscriptionPreset.objects.filter(profile=profile).count(), 1)

    def test_delete(self):
        profile = ConnectionProfile.objects.create(owner=self.budi, name="Old", host="broker.emqx.io")
        self.assertContains(self.client.get(reverse("connections:delete", args=[profile.pk])), 'Delete "Old"?')
        self.assertRedirects(self.client.post(reverse("connections:delete", args=[profile.pk])),
                             reverse("connections:list"))
        self.assertFalse(ConnectionProfile.objects.filter(pk=profile.pk).exists())
