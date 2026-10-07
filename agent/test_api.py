"""API 测试通过 TestClient 运行，不监听端口。"""

import contextlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api


class ApiTests(unittest.TestCase):
    def test_health_does_not_collect(self):
        with patch.object(api.monitor.Collector, "collect_network", return_value={}), \
                patch.object(api.monitor.Collector, "collect") as collect, \
                TestClient(api.app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})
            collect.assert_not_called()
        self.assertFalse(hasattr(api.app.state, "collector"))

    def test_status_returns_collector_output_without_changes(self):
        sample = {"timestamp": "2026-10-07T00:00:00+00:00", "errors": {},
                  "cpu": {"usage_percent": 20, "logical_cores": 4},
                  "memory": {"total_bytes": 1000}, "disk": {"path": "/"},
                  "network": {"interfaces": {}}, "system": {"hostname": "ubuntu"}}
        with patch.object(api.monitor.Collector, "collect_network", return_value={}), \
                patch.object(api.monitor.Collector, "collect", return_value=sample) as collect, \
                TestClient(api.app) as client:
            response = client.get("/api/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), sample)
            collect.assert_called_once()

    def test_partial_failure_and_recovery(self):
        with contextlib.ExitStack() as stack:
            for name in ("cpu", "disk", "network", "system"):
                stack.enter_context(patch.object(api.monitor.Collector, f"collect_{name}", return_value={"ok": True}))
            memory = stack.enter_context(patch.object(api.monitor.Collector, "collect_memory", side_effect=OSError("denied")))
            client = stack.enter_context(TestClient(api.app))
            with self.assertLogs("monitor", level="ERROR"):
                response = client.get("/api/status")
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.json()["memory"])
            self.assertIn("OSError", response.json()["errors"]["memory"])
            self.assertTrue(response.json()["cpu"]["ok"])
            self.assertEqual(client.get("/health").json(), {"status": "ok"})
            memory.side_effect = None
            memory.return_value = {"ok": True}
            self.assertEqual(client.get("/api/status").json()["errors"], {})

    def test_network_baseline_is_retained_between_requests(self):
        counters = [{"ens3": SimpleNamespace(bytes_sent=100, bytes_recv=200)},
                    {"ens3": SimpleNamespace(bytes_sent=300, bytes_recv=600)},
                    {"ens3": SimpleNamespace(bytes_sent=700, bytes_recv=1400)}]
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(api.monitor.psutil, "net_io_counters", side_effect=counters))
            times = iter([10, 12, 16])
            stack.enter_context(patch.object(api.monitor, "time", SimpleNamespace(monotonic=lambda: next(times))))
            for name in ("cpu", "memory", "disk", "system"):
                stack.enter_context(patch.object(api.monitor.Collector, f"collect_{name}", return_value={}))
            client = stack.enter_context(TestClient(api.app))
            for _ in range(2):
                network = client.get("/api/status").json()["network"]
                self.assertEqual(network["interfaces"]["ens3"]["upload_bytes_per_second"], 100)
                self.assertEqual(network["interfaces"]["ens3"]["download_bytes_per_second"], 200)

    def test_failed_warmup_can_recover(self):
        with patch.object(api.monitor.Collector, "collect_network", side_effect=[OSError("unavailable"), {"interfaces": {}}]), \
                patch.object(api.monitor.Collector, "collect_cpu", return_value={}), \
                self.assertLogs("agent.api", level="ERROR"), TestClient(api.app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/api/status").json()["network"], {"interfaces": {}})

    def test_default_binding_is_loopback(self):
        with patch.object(api.uvicorn, "run") as run:
            api.main()
        run.assert_called_once_with(api.app, host="127.0.0.1", port=8000)

    def test_missing_psutil_prevents_startup(self):
        with patch.object(api.monitor, "psutil", None):
            with self.assertRaisesRegex(RuntimeError, "psutil"):
                with TestClient(api.app):
                    pass


if __name__ == "__main__":
    unittest.main()
