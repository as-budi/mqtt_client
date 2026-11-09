"""
Daftar halaman dokumentasi pengguna MQTT Client (tahap M13), urut seperti di menu.
Kerangka, pencarian, dan tampilannya sama dengan dokumentasi IoT Platform (app userdocs di
repo IoT_platform, tahap 25).

Setiap halaman adalah satu template fragmen HTML di userdocs/templates/userdocs/pages/<slug>.html.
Fragmen dirender untuk ditampilkan (views.page) dan untuk indeks pencarian (search.py), jadi
fragmen hanya boleh bergantung pada konteks dari userdocs/context.py (tanpa pengguna).

Menambah halaman: buat fragmennya, lalu tambahkan satu baris Page di PAGES. Judul bagian di
dalam fragmen memakai <h2 id="..."> / <h3 id="...">: id itulah tujuan tautan dan pencarian.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    section: str
    summary: str

    @property
    def template(self):
        return f"userdocs/pages/{self.slug}.html"


PAGES = [
    Page("getting-started", "Getting started", "Basics",
         "What the MQTT Client does, signing in, and your first connection in a few steps."),
    Page("mqtt-basics", "MQTT in a nutshell", "Basics",
         "Brokers, topics, wildcards, QoS, retained messages and Last Will, with examples."),
    Page("account", "Your account and display", "Basics",
         "Signing in with IoT Platform, permissions, signing out, style and light/dark mode."),
    Page("connections", "Connection profiles", "Connections",
         "Broker address, WebSocket and TCP brokers, client ID, MQTT version, Last Will and certificates."),
    Page("platform-devices", "IoT Platform devices and sandbox", "Connections",
         "Connecting as one of your IoT Platform devices, and the personal MQTT sandbox."),
    Page("subscribe-publish", "Subscribe and publish", "Messages",
         "Subscriptions, publishing with QoS and retain, the JSON editor, placeholders, saved messages."),
    Page("messages", "Reading messages", "Messages",
         "The message list, filters and views, the topic tree, charts, MQTT 5 properties and export."),
    Page("device-simulator", "Behaving like a device", "Simulating devices",
         "Simulated sensors, automatic command answers, requested states, rule JSON and firmware updates."),
    Page("camera-simulator", "Camera simulator (ESP32-CAM)", "Simulating devices",
         "Answering capture commands with pictures from a test pattern, image files or your webcam."),
    Page("troubleshooting", "Troubleshooting", "Help",
         "Connection problems, relay messages, sign-in and camera issues, and how to solve them."),
]

BY_SLUG = {page.slug: page for page in PAGES}


def sections():
    """[(nama bagian, [Page, ...]), ...] dalam urutan PAGES."""
    result = []
    for page in PAGES:
        if not result or result[-1][0] != page.section:
            result.append((page.section, []))
        result[-1][1].append(page)
    return result


def neighbours(slug):
    """(halaman sebelumnya, halaman berikutnya) untuk tautan di bawah halaman."""
    index = [page.slug for page in PAGES].index(slug)
    previous = PAGES[index - 1] if index > 0 else None
    following = PAGES[index + 1] if index + 1 < len(PAGES) else None
    return previous, following
