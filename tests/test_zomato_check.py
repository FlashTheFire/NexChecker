#!/usr/bin/env python3
"""Unit tests for Zomato silent registration checker and platform registry."""

import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEXBOT_ROOT = ROOT / "NexBot"
for p in (str(ROOT), str(NEXBOT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from zomato_check import (
    normalize_mobile,
    encode_phone_to_name,
    decode_name_to_phone,
    check_zomato,
)
# pyrefly: ignore[missing-import]
from utils.platforms import get_platforms, get_platform


class TestZomatoCheckHelpers(unittest.TestCase):
    def test_normalize_mobile(self):
        self.assertEqual(normalize_mobile("9876543210"), "9876543210")
        self.assertEqual(normalize_mobile("+919876543210"), "9876543210")
        self.assertEqual(normalize_mobile("919876543210"), "9876543210")
        self.assertEqual(normalize_mobile("98765 43210"), "9876543210")
        self.assertEqual(normalize_mobile("+91 98765-43210"), "9876543210")

    def test_encode_and_decode_reversibility(self):
        numbers = ["9876543210", "6002731082", "7000000000", "8123456789"]
        for num in numbers:
            encoded = encode_phone_to_name(num)
            self.assertTrue(encoded.startswith("NexUser "))
            # Check only letters in code
            code = encoded.replace("NexUser ", "")
            self.assertEqual(len(code), 10)
            self.assertTrue(code.isalpha())
            # Decodes back to original 10 digits
            decoded = decode_name_to_phone(encoded)
            self.assertEqual(decoded, num)

    def test_invalid_mobile(self):
        res = check_zomato("12345")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("Invalid", res.get("error", ""))

    @patch("requests.post")
    def test_check_zomato_registered(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "registered": True,
            "isZomatoUser": True,
            "recommendations": 2,
        }
        mock_post.return_value = mock_resp

        res = check_zomato("9876543210")
        self.assertEqual(res["status"], "REGISTERED")
        self.assertTrue(res["registered"])
        self.assertEqual(res["recommendations"], 2)

    @patch("requests.post")
    def test_check_zomato_not_registered(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "registered": False,
            "isZomatoUser": False,
        }
        mock_post.return_value = mock_resp

        res = check_zomato("6002731082")
        self.assertEqual(res["status"], "NOT_REGISTERED")
        self.assertFalse(res["registered"])


class TestPlatformRegistry(unittest.TestCase):
    def test_zomato_registered_in_platforms(self):
        platforms = get_platforms()
        self.assertIn("zomato", platforms)
        zomato = get_platform("zomato")
        self.assertIsNotNone(zomato)
        self.assertEqual(zomato.key, "zomato")
        self.assertEqual(zomato.command, "zomato")
        self.assertEqual(zomato.country_code, "22")
        self.assertFalse(zomato.needs_warmup)
        self.assertTrue(hasattr(zomato.checker, "check_number"))
        self.assertTrue(hasattr(zomato.checker, "startup"))
        self.assertTrue(hasattr(zomato.checker, "shutdown"))


if __name__ == "__main__":
    unittest.main()
