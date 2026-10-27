"""End-to-end and integration tests for NexNum client and checker workflows."""
import asyncio
import os
import unittest
from pathlib import Path
import sys

NEXCHECKER_ROOT = Path(__file__).resolve().parent.parent
NEXBOT_DIR = NEXCHECKER_ROOT / "NexBot"
CHECKERS_DIR = NEXCHECKER_ROOT / "checkers"
for p in (str(NEXCHECKER_ROOT), str(NEXBOT_DIR), str(CHECKERS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.nexnum_api import nexnum_client


class TestNexNumE2E(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.api_key = os.getenv("NEXNUM_API_KEY", "nxn_live_834pV7wW1kimHGG2yuPD3G3c9G2Ll9LK")

    async def asyncTearDown(self):
        await nexnum_client.close()

    async def test_get_balance_structure(self):
        """Verify get_balance returns the expected structure."""
        res = await nexnum_client.get_balance(self.api_key)
        self.assertIn("ok", res)
        if res.get("ok"):
            self.assertIn("balance", res)
            self.assertTrue(isinstance(res["balance"], (int, float)))
        else:
            self.assertIn("error", res)

    async def test_invalid_status_lookup(self):
        """Lookup an invalid order id and verify error handling."""
        res = await nexnum_client.get_status(self.api_key, "invalid_nonexistent_order_id_123")
        self.assertIn("ok", res)
        self.assertFalse(res.get("ok"))


if __name__ == "__main__":
    unittest.main()
