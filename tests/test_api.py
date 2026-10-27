#!/usr/bin/env python3
"""Unit tests for NexChecker FastAPI backend endpoints."""

import unittest
import sys
from pathlib import Path
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

    def test_platforms_list(self):
        resp = client.get("/api/platforms")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("platforms", data)
        keys = [p["key"] for p in data["platforms"]]
        self.assertIn("zomato", keys)
        self.assertIn("flipkart", keys)
        self.assertIn("bigbasket", keys)

    def test_invalid_phone_check(self):
        resp = client.post("/api/checker/phone", json={"target_phone": "123", "platform": "zomato"})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
