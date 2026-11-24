#!/usr/bin/env python3
"""Unit tests for NexChecker FastAPI backend endpoints."""

import os
import unittest
import sys
from pathlib import Path

os.environ["ENVIRONMENT"] = "testing"
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
CHECKERS_ROOT = ROOT / "checkers"
NEXBOT_ROOT = ROOT / "NexBot"
for p in (str(ROOT), str(CHECKERS_ROOT), str(NEXBOT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.main import app

client = TestClient(app)


class TestNexCheckerAPI(unittest.TestCase):
    def test_health_check(self):
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("service"), "NexChecker")
        self.assertIn("engines", data)
        self.assertIn("meesho", data["engines"])

    def test_platforms_list(self):
        resp = client.get("/api/platforms")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("platforms", data)
        self.assertIn("active_count", data)
        keys = [p["key"] for p in data["platforms"]]
        self.assertIn("zomato", keys)
        self.assertIn("flipkart", keys)
        self.assertIn("bigbasket", keys)
        self.assertIn("meesho", keys)
        for p in data["platforms"]:
            self.assertIn("service_code", p)
            self.assertIn("module", p)
            self.assertIn("mechanism", p)

    def test_invalid_phone_check(self):
        resp = client.post("/api/checker/phone", json={"target_phone": "123", "platform": "meesho"})
        self.assertEqual(resp.status_code, 400)

    def test_web_ui_serving(self):
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn("zomato", resp.text.lower())
        self.assertIn("/api-docs", resp.text)

    def test_api_docs_serving(self):
        for route in ("/api-docs", "/api-docs/"):
            resp = client.get(route)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers.get("content-type", ""))
            self.assertIn("NexChecker", resp.text)
            self.assertIn("/api/v1/purchase", resp.text)
            self.assertIn("Security Layer", resp.text)
            self.assertIn("Targeted Virtual Number Purchase", resp.text)
            self.assertIn("Checker Engines", resp.text)
            self.assertIn("Rules &amp; Notes", resp.text)
            self.assertIn("X-Test-Bypass", resp.text)
            self.assertIn("dynamicLogoImg", resp.text)
            self.assertNotIn("version-badge", resp.text)
            self.assertNotIn("Error Reference", resp.text)
            self.assertNotIn("Interactive API Playground", resp.text)
            self.assertNotIn("Active Services", resp.text)
            self.assertNotIn("copyBaseUrlBtn", resp.text)
            self.assertNotIn("liveHealthPill", resp.text)
            self.assertNotIn("heroServiceStack", resp.text)

        css_resp = client.get("/static/api-docs.css")
        self.assertEqual(css_resp.status_code, 200)
        self.assertIn(".tok-key", css_resp.text)
        self.assertIn("#9cdcfe", css_resp.text)
        self.assertIn("#ce9178", css_resp.text)
        js_resp = client.get("/static/api-docs.js")
        self.assertEqual(js_resp.status_code, 200)
        self.assertIn("highlightJSON", js_resp.text)
        self.assertIn("highlightCode", js_resp.text)
        self.assertIn("el.cyclingServiceLabel.textContent = p.label;", js_resp.text)

    def test_bot_webhook_endpoint(self):
        # Empty or mock update payload
        resp = client.post("/bot/webhook", json={"update_id": 999999})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))


if __name__ == "__main__":
    unittest.main()
