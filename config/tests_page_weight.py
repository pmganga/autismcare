"""NFR 2 page weight: pages stay small for 3G, well under the 2.5 MB limit."""
import gzip
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

LIMIT_BYTES = int(2.5 * 1024 * 1024)
PAGE_BUDGET_BYTES = 50 * 1024    # one page with its CSS and JS, compressed
MAP_BYTES = 240 * 1024           # Leaflet plus about 15 map tiles, measured (only after a search)


class PageWeightTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_questions", verbosity=0)

    def compressed_size(self, url):
        r = self.client.get(url, HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(r.status_code, 200, url)
        self.assertEqual(r.get("Content-Encoding"), "gzip", f"{url} is not compressed")
        html = gzip.decompress(r.content).decode()
        total = len(r.content)
        for ref in re.findall(r'(?:href|src)="/static/([^"]+)"', html):
            total += len(gzip.compress((Path(settings.BASE_DIR) / "static" / ref).read_bytes()))
        return total

    def test_pages_within_budget(self):
        for name in ("home", "find", "login", "register", "screening", "screening-questions", "teacher-register"):
            with self.subTest(page=name):
                size = self.compressed_size(reverse(name))
                self.assertLess(size, PAGE_BUDGET_BYTES, f"{name}: {size} bytes")
                self.assertLess(size + MAP_BYTES, LIMIT_BYTES)

    def test_api_replies_are_compressed(self):
        r = self.client.get(reverse("api-questionnaire"), HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(r.get("Content-Encoding"), "gzip")
