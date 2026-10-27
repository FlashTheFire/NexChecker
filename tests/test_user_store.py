"""Unit tests for NexBot hierarchical JSON user store."""
import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
NEXCHECKER_ROOT = Path(__file__).resolve().parent.parent
NEXBOT_DIR = NEXCHECKER_ROOT / "NexBot"
CHECKERS_DIR = NEXCHECKER_ROOT / "checkers"
for p in (str(NEXCHECKER_ROOT), str(NEXBOT_DIR), str(CHECKERS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core import user_store


class TestUserStoreHierarchical(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_data_dir = user_store.DATA_DIR
        user_store.DATA_DIR = Path(self.test_dir)
        user_store.USERS_DIR = Path(self.test_dir)

    async def asyncTearDown(self):
        user_store.DATA_DIR = self.orig_data_dir
        user_store.USERS_DIR = self.orig_data_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_info_creation_and_api_key(self):
        uid = 999111
        self.assertIsNone(await user_store.get_api_key(uid))
        await user_store.set_api_key(uid, "test_api_key_123")
        self.assertEqual(await user_store.get_api_key(uid), "test_api_key_123")

        info_path = Path(self.test_dir) / str(uid) / "info.json"
        self.assertTrue(info_path.exists())
        with open(info_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["api_key"], "test_api_key_123")

    async def test_multi_service_concurrent_orders(self):
        uid = 999222
        # Order 1: Zomato
        await user_store.save_order({
            "order_id": "zomato_order_001",
            "user_id": uid,
            "platform": "zomato",
            "number": "919876543210",
            "status": "CHECKING",
            "chat_id": 12345,
            "message_id": 100,
        })
        # Order 2: Myntra
        await user_store.save_order({
            "order_id": "myntra_order_002",
            "user_id": uid,
            "platform": "myntra",
            "number": "919123456789",
            "status": "CHECKING",
            "chat_id": 12345,
            "message_id": 101,
        })

        # Verify separate files exist
        zomato_path = Path(self.test_dir) / str(uid) / "zomato_order_001.json"
        myntra_path = Path(self.test_dir) / str(uid) / "myntra_order_002.json"
        self.assertTrue(zomato_path.exists())
        self.assertTrue(myntra_path.exists())

        # Verify active orders lookup per platform
        active_z = await user_store.get_active_order(uid, "zomato")
        active_m = await user_store.get_active_order(uid, "myntra")
        self.assertIsNotNone(active_z)
        self.assertIsNotNone(active_m)
        self.assertEqual(active_z["order_id"], "zomato_order_001")
        self.assertEqual(active_m["order_id"], "myntra_order_002")

        # Update zomato OTP without touching myntra
        await user_store.update_order(uid, {"last_otp": "456789", "status": "COMPLETED"}, order_id="zomato_order_001")

        active_z_updated = await user_store.get_order(uid, "zomato_order_001")
        active_m_updated = await user_store.get_order(uid, "myntra_order_002")
        self.assertEqual(active_z_updated["last_otp"], "456789")
        self.assertEqual(active_z_updated["status"], "COMPLETED")
        self.assertEqual(active_m_updated["status"], "CHECKING")
        self.assertIsNone(active_m_updated.get("last_otp"))

    async def test_legacy_monolithic_migration(self):
        uid = 888333
        legacy_file = Path(self.test_dir) / f"{uid}.json"
        legacy_data = {
            "api_key": "legacy_key_abc",
            "preferences": {"filter_zomato": "REGISTERED"},
            "stats": {"total_checked": 5, "registered": 3},
            "last_order": {
                "order_id": "legacy_ord_999",
                "platform": "zomato",
                "number": "919000000000",
                "status": "COMPLETED",
                "last_otp": "112233",
            },
            "purchases": [
                {
                    "order_id": "legacy_ord_888",
                    "platform": "myntra",
                    "number": "918000000000",
                    "status": "REFUNDED",
                }
            ],
        }
        with open(legacy_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        # Trigger read, which triggers migration
        info = await user_store.load_user_info(uid)
        self.assertEqual(info["api_key"], "legacy_key_abc")
        self.assertEqual(info["preferences"]["filter_zomato"], "REGISTERED")
        self.assertEqual(info["stats"]["total_checked"], 5)

        # Legacy file deleted / unlinked
        self.assertFalse(legacy_file.exists())

        # Check new structure
        info_path = Path(self.test_dir) / str(uid) / "info.json"
        ord_999_path = Path(self.test_dir) / str(uid) / "legacy_ord_999.json"
        ord_888_path = Path(self.test_dir) / str(uid) / "legacy_ord_888.json"
        self.assertTrue(info_path.exists())
        self.assertTrue(ord_999_path.exists())
        self.assertTrue(ord_888_path.exists())

        # Verify order content
        ord_999 = await user_store.get_order(uid, "legacy_ord_999")
        self.assertEqual(ord_999["last_otp"], "112233")


if __name__ == "__main__":
    unittest.main()
