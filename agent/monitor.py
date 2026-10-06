"""本机监控 Agent：只读取系统指标，不进行网络上报或远程操作。"""

import argparse
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import platform
import socket
import sys
import time

try:
    import psutil
except ImportError:
    psutil = None

LOGGER = logging.getLogger("monitor")


def positive_interval(value):
    """拒绝非正数、NaN 和无穷大，防止异常等待或空转。"""
    try:
        interval = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("采集间隔必须是正数（秒）") from exc
    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError("采集间隔必须是有限的正数（秒）")
    return interval


def root_partition():
    # Windows 没有 Linux 的 / 根分区，本地测试使用 Windows 所在的系统盘。
    if os.name == "nt":
        return Path(os.environ.get("SystemRoot", "C:\\Windows")).anchor
    return "/"


class Collector:
    def __init__(self):
        self.previous_network = {}
        self.previous_network_time = None

    def collect_cpu(self):
        # 独立采样 0.2 秒，避免首次非阻塞调用得到无意义的 0%。
        return {
            "usage_percent": psutil.cpu_percent(interval=0.2),
            "logical_cores": psutil.cpu_count(logical=True),
        }

    def collect_memory(self):
        memory = psutil.virtual_memory()
        return {
            "total_bytes": memory.total,
            "used_bytes": memory.used,
            "available_bytes": memory.available,
            "usage_percent": memory.percent,
        }

    def collect_disk(self):
        path = root_partition()
        disk = psutil.disk_usage(path)
        return {
            "path": path,
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "usage_percent": disk.percent,
        }

    def collect_network(self):
        counters = psutil.net_io_counters(pernic=True, nowrap=True) or {}
        # 单调时钟不受系统校时影响，速率使用实际经过时间而不是配置间隔。
        now = time.monotonic()
        elapsed = None if self.previous_network_time is None else now - self.previous_network_time
        interfaces = {}
        for name, counter in counters.items():
            previous = self.previous_network.get(name)
            upload = download = None
            if previous is not None and elapsed is not None and elapsed > 0:
                sent_delta = counter.bytes_sent - previous.bytes_sent
                received_delta = counter.bytes_recv - previous.bytes_recv
                # 接口重新出现或计数器重置时，不输出负速率；以新计数为基线。
                if sent_delta >= 0:
                    upload = round(sent_delta / elapsed, 2)
                if received_delta >= 0:
                    download = round(received_delta / elapsed, 2)
            interfaces[name] = {
                "bytes_sent": counter.bytes_sent,
                "bytes_received": counter.bytes_recv,
                "upload_bytes_per_second": upload,
                "download_bytes_per_second": download,
            }

        # 仅在成功读取后更新基线；失败后恢复时仍按完整经过时间计算。
        self.previous_network = counters
        self.previous_network_time = now
        return {
            "sample_seconds": round(elapsed, 4) if elapsed is not None else None,
            "interfaces": interfaces,
        }

    def collect_system(self):
        os_name = platform.system()
        os_version = platform.platform()
        if os_name == "Linux":
            # Python 3.10+ 标准库读取 /etc/os-release，不执行系统命令。
            try:
                os_version = platform.freedesktop_os_release().get("PRETTY_NAME", os_version)
            except OSError as exc:
                LOGGER.warning("读取 Linux 发行版信息失败，使用内核信息：%s", exc)
        boot_time = psutil.boot_time()
        return {
            "hostname": socket.gethostname(),
            "os": os_name,
            "os_version": os_version,
            "kernel_version": platform.release(),
            "boot_time": datetime.fromtimestamp(boot_time, timezone.utc).isoformat(),
            "uptime_seconds": round(max(0, time.time() - boot_time), 2),
        }

    def collect(self):
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "errors": {},
        }
        collectors = {
            "cpu": self.collect_cpu,
            "memory": self.collect_memory,
            "disk": self.collect_disk,
            "network": self.collect_network,
            "system": self.collect_system,
        }
        for name, collect_metric in collectors.items():
            try:
                result[name] = collect_metric()
            except Exception as exc:
                # 在每个采集边界隔离异常，让其他指标及下一轮采集继续执行。
                result[name] = None
                result["errors"][name] = f"{type(exc).__name__}: {exc}"
                LOGGER.exception("%s 采集失败", name)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="轻量级本机监控 Agent，输出 JSON Lines")
    parser.add_argument("--interval", type=positive_interval, default=30.0,
                        help="两轮采集开始时间之间的间隔，单位秒，默认 30")
    parser.add_argument("--once", action="store_true", help="采集一次并退出")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if psutil is None:
        LOGGER.error("缺少 psutil，请使用虚拟环境的 Python 运行：python -m pip install -r agent/requirements.txt")
        return 1

    collector = Collector()
    try:
        # 提前建立网络基线，使 --once 也能输出有意义的网络速率。
        try:
            collector.collect_network()
        except Exception:
            LOGGER.exception("网络预采样失败，将在正式采集时重试")
        time.sleep(1.0)

        while True:
            started = time.monotonic()
            result = collector.collect()
            print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
            if args.once:
                return 0
            # 扣除本轮采集时间；采集耗时超过间隔时，下一轮立即开始。
            time.sleep(max(0, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        LOGGER.info("收到 Ctrl+C，Agent 已退出")
        return 0
    except BrokenPipeError:
        # 输出管道被关闭时停止，不再向已关闭的管道写入退出信息。
        sys.stdout = open(os.devnull, "w")
        return 0


if __name__ == "__main__":
    sys.exit(main())
