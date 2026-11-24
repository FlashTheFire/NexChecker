#!/usr/bin/env python3
"""Comprehensive unit and integration test suite for NexChecker Purchase API & Cancel Queue."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ["ENVIRONMENT"] = "testing"

ROOT = Path(__file__).resolve().parent.parent
CHECKERS_ROOT = ROOT / "checkers"
NEXBOT_ROOT = ROOT / "NexBot"
for p in (str(ROOT), str(CHECKERS_ROOT), str(NEXBOT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient

from api.cancel_queue import CancelQueueManager, cancel_queue
from api.main import app
from core.nexnum_api import NexNumStatus

client = TestClient(app)


class TestPurchaseAPI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Clear cancel queue
        cancel_queue._queue.clear()

    def test_missing_nexnum_key(self):
        resp = client.post("/api/v1/purchase", json={"platform": "zomato", "target_status": "NOT_REGISTERED"})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data["detail"]["error"], "NEXNUM_KEY_REQUIRED")

    def test_invalid_target_status(self):
        resp = client.post(
            "/api/v1/purchase",
            json={
                "platform": "zomato",
                "target_status": "INVALID_STATUS",
                "api_key": "test_key",
            },
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data["detail"]["error"], "INVALID_TARGET_STATUS")

    def test_api_access_key_enforcement(self):
        with patch.dict(os.environ, {"API_ACCESS_KEY": "secret_access_token_123"}):
            # Missing key -> 401
            resp_missing = client.post(
                "/api/v1/purchase",
                json={"platform": "zomato", "api_key": "test_key"},
            )
            self.assertEqual(resp_missing.status_code, 401)

            # Invalid key -> 401
            resp_invalid = client.post(
                "/api/v1/purchase",
                headers={"X-API-Key": "wrong_key"},
                json={"platform": "zomato", "api_key": "test_key"},
            )
            self.assertEqual(resp_invalid.status_code, 401)

            # Valid key -> proceeds (fails on mocked purchase logic, not auth)
            with patch("api.purchase_service.nexnum_client.get_number", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = {
                    "ok": True,
                    "order_id": "111",
                    "number": "919876543210",
                    "cost": 9.0,
                }
                with patch("api.main._execute_check", new_callable=AsyncMock) as mock_check:
                    mock_check.return_value = {"status": "NOT_REGISTERED"}
                    resp_valid = client.post(
                        "/api/v1/purchase",
                        headers={"X-API-Key": "secret_access_token_123"},
                        json={"platform": "zomato", "api_key": "test_key", "target_status": "NOT_REGISTERED"},
                    )
                    self.assertEqual(resp_valid.status_code, 200)

    def test_successful_match_first_attempt(self):
        with patch("api.purchase_service.nexnum_client.get_number", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "ok": True,
                "order_id": "order_abc_123",
                "number": "919876543210",
                "cost": 9.0,
            }
            with patch("api.main._execute_check", new_callable=AsyncMock) as mock_check:
                mock_check.return_value = {"status": "NOT_REGISTERED"}

                resp = client.post(
                    "/api/v1/purchase",
                    headers={"X-NexNum-Key": "valid_user_key"},
                    json={
                        "platform": "zomato",
                        "target_status": "NOT_REGISTERED",
                        "service_code": "dy",
                    },
                )
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertTrue(data["success"])
                self.assertEqual(data["order_id"], "order_abc_123")
                self.assertEqual(data["clean_mobile"], "9876543210")
                self.assertEqual(data["status"], "NOT_REGISTERED")
                self.assertEqual(data["attempts_taken"], 1)
                self.assertIn("nexnum_direct_usage", data)
                self.assertIn("order_abc_123", data["nexnum_direct_usage"]["get_status_url"])
                self.assertTrue(data["nexnum_direct_usage"]["get_status_url"].endswith("&format=json"))
                self.assertTrue(data["nexnum_direct_usage"]["cancel_url"].endswith("&format=json"))
                self.assertNotIn("api_key", data["nexnum_direct_usage"]["get_status_url"])
                self.assertNotIn("api_key", data["nexnum_direct_usage"]["cancel_url"])

    def test_mismatch_discards_and_retries(self):
        with patch("api.purchase_service.nexnum_client.get_number", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                {"ok": True, "order_id": "order_reg_1", "number": "919876543211", "cost": 9.0},
                {"ok": True, "order_id": "order_fresh_2", "number": "919876543212", "cost": 9.0},
            ]
            with patch("api.main._execute_check", new_callable=AsyncMock) as mock_check:
                # Attempt 1 returns REGISTERED (mismatch), Attempt 2 returns NOT_REGISTERED (match)
                mock_check.side_effect = [
                    {"status": "REGISTERED"},
                    {"status": "NOT_REGISTERED"},
                ]
                with patch("api.cancel_queue.nexnum_client.set_status", new_callable=AsyncMock) as mock_set:
                    mock_set.return_value = {"ok": False, "early_denied": True}

                    resp = client.post(
                        "/api/v1/purchase",
                        json={
                            "platform": "zomato",
                            "target_status": "NOT_REGISTERED",
                            "api_key": "user_key_xyz",
                            "max_attempts": 3,
                        },
                    )
                    self.assertEqual(resp.status_code, 200)
                    data = resp.json()
                    self.assertTrue(data["success"])
                    self.assertEqual(data["order_id"], "order_fresh_2")
                    self.assertEqual(data["attempts_taken"], 2)
                    self.assertEqual(len(data["discarded_orders"]), 1)
                    self.assertEqual(data["discarded_orders"][0]["order_id"], "order_reg_1")
                    self.assertEqual(data["discarded_orders"][0]["cancellation"], "QUEUED_DEFERRED")

    def test_consecutive_inconclusive_breaks_loop(self):
        """User Q5 specification: if consecutive inconclusive/error occurs twice, stop loop and return error."""
        with patch("api.purchase_service.nexnum_client.get_number", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                {"ok": True, "order_id": "order_err_1", "number": "919876543213", "cost": 9.0},
                {"ok": True, "order_id": "order_err_2", "number": "919876543214", "cost": 9.0},
                {"ok": True, "order_id": "order_err_3", "number": "919876543215", "cost": 9.0},
            ]
            with patch("api.main._execute_check", new_callable=AsyncMock) as mock_check:
                # Both attempts return ERROR
                mock_check.side_effect = [
                    {"status": "ERROR", "error": "Zomato service timeout"},
                    {"status": "ERROR", "error": "Zomato service timeout"},
                ]
                with patch("api.cancel_queue.nexnum_client.set_status", new_callable=AsyncMock) as mock_set:
                    mock_set.return_value = {"ok": False, "early_denied": True}

                    resp = client.post(
                        "/api/v1/purchase",
                        json={
                            "platform": "zomato",
                            "target_status": "NOT_REGISTERED",
                            "api_key": "user_key_xyz",
                            "max_attempts": 5,
                        },
                    )
                    self.assertEqual(resp.status_code, 422)
                    data = resp.json()["detail"]
                    self.assertFalse(data["success"])
                    self.assertEqual(data["error"], "CHECKER_INCONCLUSIVE")
                    self.assertEqual(data["attempts_taken"], 2)  # Stopped at attempt 2
                    self.assertEqual(len(data["discarded_orders"]), 2)

    def test_nexnum_fatal_no_balance(self):
        with patch("api.purchase_service.nexnum_client.get_number", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "ok": False,
                "status": NexNumStatus.NO_BALANCE,
                "error": "Account balance zero",
            }
            resp = client.post(
                "/api/v1/purchase",
                json={
                    "platform": "zomato",
                    "target_status": "NOT_REGISTERED",
                    "api_key": "user_key_xyz",
                },
            )
            self.assertEqual(resp.status_code, 402)
            data = resp.json()["detail"]
            self.assertFalse(data["success"])
            self.assertEqual(data["error"], NexNumStatus.NO_BALANCE)

    def test_max_attempts_exhausted(self):
        with patch("api.purchase_service.nexnum_client.get_number", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "ok": True,
                "order_id": "order_exhausted",
                "number": "919876543299",
                "cost": 9.0,
            }
            with patch("api.main._execute_check", new_callable=AsyncMock) as mock_check:
                mock_check.return_value = {"status": "REGISTERED"}  # Always mismatch for NOT_REGISTERED
                with patch("api.cancel_queue.nexnum_client.set_status", new_callable=AsyncMock) as mock_set:
                    mock_set.return_value = {"ok": True}

                    resp = client.post(
                        "/api/v1/purchase",
                        json={
                            "platform": "zomato",
                            "target_status": "NOT_REGISTERED",
                            "api_key": "user_key_xyz",
                            "max_attempts": 2,
                        },
                    )
                    self.assertEqual(resp.status_code, 422)
                    data = resp.json()["detail"]
                    self.assertFalse(data["success"])
                    self.assertEqual(data["error"], "MAX_ATTEMPTS_EXHAUSTED")
                    self.assertEqual(data["attempts_taken"], 2)


class TestCancelQueueManager(unittest.IsolatedAsyncioTestCase):
    async def test_immediate_cancel_success(self):
        manager = CancelQueueManager()
        with patch("api.cancel_queue.nexnum_client.set_status", new_callable=AsyncMock) as mock_set:
            mock_set.return_value = {"ok": True, "status": "ACCESS_CANCEL"}
            res = await manager.try_immediate_or_enqueue("api_k", "order_imm_1")
            self.assertTrue(res)
            self.assertEqual(manager.queue_size, 0)

    async def test_deferred_enqueue_on_cooldown(self):
        manager = CancelQueueManager()
        with patch("api.cancel_queue.nexnum_client.set_status", new_callable=AsyncMock) as mock_set:
            mock_set.return_value = {"ok": False, "early_denied": True, "code": "EARLY_CANCEL_DENIED"}
            res = await manager.try_immediate_or_enqueue("api_k", "order_defer_1")
            self.assertFalse(res)
            self.assertEqual(manager.queue_size, 1)

            # Idempotent enqueue
            await manager.enqueue("api_k", "order_defer_1")
            self.assertEqual(manager.queue_size, 1)

    async def test_worker_lifecycle(self):
        manager = CancelQueueManager()
        manager.start()
        self.assertTrue(manager._is_running)
        self.assertIsNotNone(manager._worker_task)
        await manager.stop()
        self.assertFalse(manager._is_running)
        self.assertIsNone(manager._worker_task)


if __name__ == "__main__":
    unittest.main()
