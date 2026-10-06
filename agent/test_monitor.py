"""使用标准库 unittest 和模拟接口测试，不连接服务器。"""

import contextlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import monitor


def counter(sent, received):
    return SimpleNamespace(bytes_sent=sent, bytes_recv=received)


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.collector = monitor.Collector()
        # 即使机器未安装 psutil，也能验证计算和异常处理逻辑。
        self.fake_psutil = SimpleNamespace(net_io_counters=lambda **kwargs: {})
        self.patcher = patch.object(monitor, "psutil", self.fake_psutil)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def sample(self, now, counters):
        with patch.object(self.fake_psutil, "net_io_counters", return_value=counters), \
                patch.object(monitor.time, "monotonic", return_value=now):
            return self.collector.collect_network()

    def test_rates_use_actual_elapsed_time(self):
        first = self.sample(10, {"eth0": counter(1000, 2000)})
        self.assertIsNone(first["interfaces"]["eth0"]["upload_bytes_per_second"])
        second = self.sample(14, {"eth0": counter(1800, 4000)})
        self.assertEqual(second["sample_seconds"], 4)
        self.assertEqual(second["interfaces"]["eth0"]["upload_bytes_per_second"], 200)
        self.assertEqual(second["interfaces"]["eth0"]["download_bytes_per_second"], 500)

    def test_reset_and_new_interface_have_unknown_rates(self):
        self.sample(10, {"eth0": counter(1000, 2000)})
        result = self.sample(12, {"eth0": counter(1, 2), "eth1": counter(300, 400)})
        for interface in result["interfaces"].values():
            self.assertIsNone(interface["upload_bytes_per_second"])
            self.assertIsNone(interface["download_bytes_per_second"])
        next_result = self.sample(14, {"eth0": counter(101, 202)})
        self.assertEqual(next_result["interfaces"]["eth0"]["upload_bytes_per_second"], 50)

    def test_removed_interface_does_not_reuse_old_baseline(self):
        self.sample(10, {"eth0": counter(1000, 2000)})
        self.sample(12, {})
        result = self.sample(14, {"eth0": counter(1800, 4000)})
        self.assertIsNone(result["interfaces"]["eth0"]["upload_bytes_per_second"])

    def test_network_failure_preserves_baseline(self):
        self.sample(10, {"eth0": counter(1000, 2000)})
        with patch.object(self.fake_psutil, "net_io_counters", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                self.collector.collect_network()
        result = self.sample(16, {"eth0": counter(1600, 3200)})
        self.assertEqual(result["sample_seconds"], 6)
        self.assertEqual(result["interfaces"]["eth0"]["download_bytes_per_second"], 200)

    def test_zero_elapsed_does_not_divide_by_zero(self):
        self.sample(10, {"eth0": counter(1000, 2000)})
        result = self.sample(10, {"eth0": counter(1100, 2200)})
        self.assertIsNone(result["interfaces"]["eth0"]["upload_bytes_per_second"])


class CollectorTests(unittest.TestCase):
    def test_ubuntu_distribution_and_root_partition(self):
        collector = monitor.Collector()
        with patch.object(monitor, "os", SimpleNamespace(name="posix")), \
                patch.object(monitor.platform, "system", return_value="Linux"), \
                patch.object(monitor.platform, "freedesktop_os_release", return_value={"PRETTY_NAME": "Ubuntu 24.04.3 LTS"}), \
                patch.object(monitor, "psutil", SimpleNamespace(boot_time=lambda: 100)):
            self.assertEqual(monitor.root_partition(), "/")
            self.assertEqual(collector.collect_system()["os_version"], "Ubuntu 24.04.3 LTS")

    def test_distribution_file_failure_falls_back(self):
        with patch.object(monitor.platform, "system", return_value="Linux"), \
                patch.object(monitor.platform, "platform", return_value="Linux-test-kernel"), \
                patch.object(monitor.platform, "freedesktop_os_release", side_effect=OSError("missing file")), \
                patch.object(monitor, "psutil", SimpleNamespace(boot_time=lambda: 100)), \
                self.assertLogs("monitor", level="WARNING"):
            self.assertEqual(monitor.Collector().collect_system()["os_version"], "Linux-test-kernel")

    def test_metric_failure_is_isolated_and_can_recover(self):
        collector = monitor.Collector()
        with contextlib.ExitStack() as stack:
            for name in ("cpu", "disk", "network", "system"):
                stack.enter_context(patch.object(collector, f"collect_{name}", return_value={"ok": True}))
            memory = stack.enter_context(patch.object(collector, "collect_memory", side_effect=OSError("denied")))
            with self.assertLogs("monitor", level="ERROR"):
                result = collector.collect()
            self.assertIsNone(result["memory"])
            self.assertIn("OSError", result["errors"]["memory"])
            self.assertTrue(result["cpu"]["ok"])
            memory.side_effect = None
            memory.return_value = {"ok": True}
            self.assertEqual(collector.collect()["errors"], {})

    def test_platform_metrics_and_units(self):
        fake = SimpleNamespace(
            cpu_percent=lambda **kwargs: 25.5,
            cpu_count=lambda **kwargs: 8,
            virtual_memory=lambda: SimpleNamespace(total=1000, used=600, available=300, percent=70),
            disk_usage=lambda path: SimpleNamespace(total=2000, used=500, free=1500, percent=25),
            boot_time=lambda: 100,
        )
        collector = monitor.Collector()
        with patch.object(monitor, "psutil", fake), \
                patch.object(monitor, "root_partition", return_value="/"), \
                patch.object(monitor.time, "time", return_value=160):
            self.assertEqual(collector.collect_cpu(), {"usage_percent": 25.5, "logical_cores": 8})
            self.assertEqual(collector.collect_memory()["used_bytes"], 600)
            self.assertEqual(collector.collect_memory()["usage_percent"], 70)
            self.assertEqual(collector.collect_disk()["path"], "/")
            self.assertEqual(collector.collect_system()["uptime_seconds"], 60)


class CliTests(unittest.TestCase):
    def test_invalid_intervals(self):
        for value in ("0", "-1", "nan", "inf", "abc"):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    monitor.main(["--interval", value])
                self.assertEqual(result.exception.code, 2)

    def test_once_outputs_one_json_record(self):
        output = io.StringIO()
        with patch.object(monitor, "psutil", object()), \
                patch.object(monitor.Collector, "collect_network", return_value={}), \
                patch.object(monitor.Collector, "collect", return_value={"errors": {}, "cpu": {"usage_percent": 20}}), \
                patch.object(monitor.time, "sleep"), contextlib.redirect_stdout(output):
            self.assertEqual(monitor.main(["--once"]), 0)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(output.getvalue())["cpu"]["usage_percent"], 20)

    def test_ctrl_c_while_waiting_exits_cleanly(self):
        output = io.StringIO()
        with patch.object(monitor, "psutil", object()), \
                patch.object(monitor.Collector, "collect_network", return_value={}), \
                patch.object(monitor.Collector, "collect", return_value={"errors": {}}), \
                patch.object(monitor.time, "sleep", side_effect=[None, KeyboardInterrupt]), \
                contextlib.redirect_stdout(output), self.assertLogs("monitor", level="INFO"):
            self.assertEqual(monitor.main([]), 0)
        self.assertEqual(len(output.getvalue().splitlines()), 1)

    def test_missing_dependency_has_helpful_error(self):
        with patch.object(monitor, "psutil", None), self.assertLogs("monitor", level="ERROR"):
            self.assertEqual(monitor.main(["--once"]), 1)


if __name__ == "__main__":
    unittest.main()
