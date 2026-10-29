#!/usr/bin/env python3
"""Unit tests for Myntra silent registration checker and platform registry."""

import asyncio
import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEXBOT_ROOT = ROOT / "NexBot"
CHECKERS_ROOT = ROOT / "checkers"
for p in (str(ROOT), str(NEXBOT_ROOT), str(CHECKERS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from checkers.myntra_check import (
        clean_phone,
        normalize_mobile,
        check_myntra,
        check_myntra_sync,
        check_myntra_async,
        MyntraClient,
        MyntraChecker,
        myntra_checker,
    )
except ImportError:
    from myntra_check import (
        clean_phone,
        normalize_mobile,
        check_myntra,
        check_myntra_sync,
        check_myntra_async,
        MyntraClient,
        MyntraChecker,
        myntra_checker,
    )

from utils.platforms import get_platforms, get_platform


class TestMyntraCheckHelpers(unittest.TestCase):
    def test_clean_phone(self):
        self.assertEqual(clean_phone("9876543210"), "9876543210")
        self.assertEqual(clean_phone("+919876543210"), "9876543210")
        self.assertEqual(clean_phone("919876543210"), "9876543210")
        self.assertEqual(clean_phone("98765 43210"), "9876543210")
        self.assertEqual(clean_phone("+91 98765-43210"), "9876543210")
        self.assertEqual(normalize_mobile("+91 98765-43210"), "9876543210")

    def test_invalid_mobile(self):
        res = check_myntra_sync("12345")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("invalid 10-digit", res.get("error", "").lower())

    @patch.object(MyntraClient, "check_number")
    def test_check_myntra_registered(self, mock_check_number):
        from core.myntra_api import CheckResult
        mock_check_number.return_value = CheckResult(
            number="9027936246",
            registered=True,
            fresh=False,
            raw={"number": "9027936246", "registered": True},
        )

        res = check_myntra_sync("9027936246")
        self.assertEqual(res["status"], "REGISTERED")
        self.assertTrue(res["registered"])
        self.assertFalse(res["fresh"])
        self.assertEqual(res["mobile"], "9027936246")

    @patch.object(MyntraClient, "check_number")
    def test_check_myntra_not_registered(self, mock_check_number):
        from core.myntra_api import CheckResult
        mock_check_number.return_value = CheckResult(
            number="9999999999",
            registered=False,
            fresh=True,
            raw={"number": "9999999999", "registered": False},
        )

        res = check_myntra_sync("9999999999")
        self.assertEqual(res["status"], "NOT_REGISTERED")
        self.assertFalse(res["registered"])
        self.assertTrue(res["fresh"])
        self.assertEqual(res["mobile"], "9999999999")

    @patch.object(MyntraClient, "check_number_async")
    def test_check_myntra_async(self, mock_check_async):
        from core.myntra_api import CheckResult
        mock_check_async.return_value = CheckResult(
            number="9027936246",
            registered=True,
            fresh=False,
            raw={"number": "9027936246", "registered": True},
        )

        res = asyncio.run(check_myntra("9027936246"))
        self.assertEqual(res["status"], "REGISTERED")
        self.assertTrue(res["registered"])
        self.assertEqual(res["via"], "api")


class TestMyntraPlatformRegistry(unittest.TestCase):
    def test_myntra_registered_in_platforms(self):
        platforms = get_platforms()
        self.assertIn("myntra", platforms)
        myntra = get_platform("myntra")
        self.assertIsNotNone(myntra)
        self.assertEqual(myntra.key, "myntra")
        self.assertEqual(myntra.command, "myntra")
        self.assertFalse(myntra.needs_warmup)
        self.assertEqual(myntra.icon, "📦")


if __name__ == "__main__":
    unittest.main()
