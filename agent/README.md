# 轻量级服务器监控 Agent

使用 Python 3.10+ 和 psutil 读取本机指标。主要面向 Ubuntu Linux，同时支持 Windows 本地测试。
Ubuntu 22.04 / 24.04 自带的 Python 版本满足要求（仍需环境已提供 pip 和 venv）。
只需普通用户权限，不修改系统配置、不执行 SSH 或远程命令。支持 CLI 和本地 HTTP API，
不会主动向外部服务上报监控数据。
现有 Dashboard 仍然使用模拟数据，这一版尚未将 Agent 与网页连接。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `monitor.py` | 指标采集、网络速率计算、命令行参数和定时循环 |
| `api.py` | FastAPI HTTP 接口和仅监听本机的 Uvicorn 启动入口 |
| `requirements.txt` | 运行依赖：psutil、FastAPI、Uvicorn |
| `requirements-test.txt` | 运行依赖及 TestClient 所需的 httpx，测试继续使用 unittest |
| `test_api.py` | API 输出、健康检查、异常恢复、网络基线及默认监听地址测试 |
| `test_monitor.py` | 标准库 unittest 测试，覆盖速率、异常恢复、参数和退出 |
| `.gitignore` | 忽略虚拟环境及 Python 缓存 |

对照 Java：`Collector` 类负责采集；Python 字典类似 `Map`；`json.dumps()` 将字典序列化成 JSON。
`main()` 是程序入口，`argparse` 解析命令行参数，`logging` 负责日志。

## Windows 本地安装和运行

以下命令在 PowerShell 中执行。无需激活虚拟环境，也无需修改 PowerShell 执行策略。
如果你的 Python 命令是 `py -3`，把创建虚拟环境的 `python` 替换为 `py -3`。

```powershell
cd D:\Projects\vibe-coding-learning
python --version
python -m venv agent/.venv
& ./agent/.venv/Scripts/python.exe -m pip install -r agent/requirements.txt

# 单次采集：约 1.2 秒后输出一条 JSON，然后退出
& ./agent/.venv/Scripts/python.exe agent/monitor.py --once

# 每 5 秒采集，便于观察；按 Ctrl+C 退出
& ./agent/.venv/Scripts/python.exe agent/monitor.py --interval 5

# 默认每 30 秒采集
& ./agent/.venv/Scripts/python.exe agent/monitor.py
```

安装只在项目虚拟环境中添加依赖，不需要管理员权限。
首次启动先等待 1 秒建立网络基线，CPU 每轮单独采样 0.2 秒。
默认间隔为 30 秒，可用 `--interval` 指定任意有限正数（支持小数）。
间隔以两轮采集开始时间为准；如果采集耗时超过间隔，则下一轮立即开始，实际间隔会变长。

Windows 会读取本机真实指标，磁盘 `path` 为系统盘（通常为 `C:\`）；Linux 为 `/`。
两者使用相同 JSON 结构，但 Windows 测试不等同于 Linux 环境验证。

## Ubuntu 安装和运行

在已具有 Python 3.10+、pip 和 venv 的 Linux 主机上，由普通用户手动执行：

```bash
cd /path/to/vibe-coding-learning
python3 -m venv agent/.venv
./agent/.venv/bin/python -m pip install -r agent/requirements.txt
./agent/.venv/bin/python agent/monitor.py --once
./agent/.venv/bin/python agent/monitor.py --interval 30
```

如果系统没有 Python/venv，请先在已有的开发环境中测试。本项目不自动安装系统软件或部署服务。
Ubuntu 上 `system.os_version` 优先显示发行版名称，例如 `Ubuntu 24.04.3 LTS`，
`system.kernel_version` 单独显示 Linux 内核版本。磁盘固定采集 `/` 所在分区，
网络自动识别接口名称，无需写死 `eth0`，支持 Ubuntu 常见的 `ens3`、`enp0s3` 等接口。

## JSON 输出和单位

标准输出每行是一条完整 JSON（JSON Lines），错误和退出日志输出到标准错误，不混入 JSON。
每条记录包含：

| 字段 | 含义 |
| --- | --- |
| `timestamp` | UTC ISO 8601 采集时间，带时区 |
| `cpu.usage_percent` / `logical_cores` | CPU 使用率（0～100）及逻辑核心数 |
| `memory.total_bytes` / `used_bytes` / `available_bytes` | 内存总量、psutil 已使用量和可用量，单位字节 |
| `memory.usage_percent` | psutil 内存使用率；基于 `(total - available) / total` |
| `disk.path` / `total_bytes` / `used_bytes` / `free_bytes` / `usage_percent` | 根分区容量及使用率 |
| `network.sample_seconds` | 距上次成功网络读取的实际秒数 |
| `network.interfaces` | 按接口名分组，包含物理接口、虚拟接口和回环接口 |
| `bytes_sent` / `bytes_received` | 各网络接口累计发送和接收字节数 |
| `upload_bytes_per_second` / `download_bytes_per_second` | 各接口平均上传和下载速率，单位 B/s |
| `system.hostname` / `os` / `os_version` / `kernel_version` | 主机名、系统类型、发行版/系统版本及内核版本 |
| `system.boot_time` / `uptime_seconds` | UTC 启动时间和系统运行秒数 |
| `errors` | 本轮失败指标及错误描述；成功时为 `{}` |

内存 `used_bytes` 与 `usage_percent` 采用 psutil 各自的定义，Linux 缓存等因素会导致
`used_bytes / total_bytes` 不等于 `usage_percent / 100`。
Linux 磁盘使用率考虑普通用户不可用的保留空间，因此也可能不等于简单的 `used / total`。

网络速率公式：`(本次累计字节数 - 上次累计字节数) / 实际经过秒数`。
使用单调时钟计时，系统校时不会改变速率计算。计数器通过 psutil 的 `nowrap=True` 处理回绕。
没有基线的新接口、接口计数重置或首次预采样失败后的第一条记录，其速率为 `null`，不伪造为 0。
没有接口时 `interfaces` 为 `{}`。某项采集失败时该项为 `null`，错误记录在 `errors` 和标准错误；
其他采集继续，下一轮会重试。Linux 发行版文件不可读时记录警告，系统版本回退到内核信息。

例如，一个网络接口的记录可能为：

```json
{
  "bytes_sent": 1048576,
  "bytes_received": 2097152,
  "upload_bytes_per_second": 1024.0,
  "download_bytes_per_second": 2048.0
}
```

字节换算为 GiB：除以 `1024 ** 3`；B/s 换算为 KiB/s：除以 `1024`；B/s 换算为 bit/s：乘以 `8`。
退出码：正常单次结束或 Ctrl+C 为 0，缺少 psutil 为 1，无效参数为 2。
单项采集失败仍会输出有效 JSON，检查 `errors` 判断本轮是否完整。

## 测试方法

### 自动测试

在项目根目录执行。TestClient 测试不监听真实端口，无需远程服务器：

```powershell
& ./agent/.venv/Scripts/python.exe -m pip install -r agent/requirements-test.txt
& ./agent/.venv/Scripts/python.exe -m unittest discover -s agent -p "test_*.py" -v
```

Linux 对应命令：

```bash
./agent/.venv/bin/python -m pip install -r agent/requirements-test.txt
./agent/.venv/bin/python -m unittest discover -s agent -p 'test_*.py' -v
```

测试使用模拟指标验证：实际时间的速率计算、新接口、接口消失、计数重置、零时间差、
网络失败后的恢复、单项异常隔离、输出 JSON、参数校验和 Ctrl+C 优雅退出。
只验证旧 CLI 逻辑且未安装依赖时，可以运行 `python -m unittest discover -s agent -p 'test_monitor.py' -v`。
完整测试需先安装 `requirements-test.txt`。API 测试还验证健康检查不触发采集、接口输出保持原结构、
单项异常与恢复、连续请求的网络基线和默认绑定地址。

### Windows 真实采集检查

```powershell
# 转换 JSON，确认错误为空，并查看 CPU / 内存 / 系统信息
$sample = & ./agent/.venv/Scripts/python.exe agent/monitor.py --once | ConvertFrom-Json
$sample.errors
$sample.cpu
$sample.memory
$sample.disk
$sample.network.interfaces
$sample.system

# 持续观察后按 Ctrl+C，确认没有异常堆栈
& ./agent/.venv/Scripts/python.exe agent/monitor.py --interval 2
```

可以与任务管理器的 CPU、内存和网络页面做大致比较。采样窗口、内存统计口径和接口范围不同，
数值不要求完全一致。网络空闲时速率为 0 是正常的，无需为了测试主动连接任何服务器。

输出也可保存到本地文件：

```powershell
& ./agent/.venv/Scripts/python.exe agent/monitor.py --once | Set-Content -Encoding utf8 sample.jsonl
```

## 本地 HTTP API

### Windows 启动和调用

在项目根目录的 PowerShell 终端运行：

```powershell
& ./agent/.venv/Scripts/python.exe -m pip install -r agent/requirements.txt
& ./agent/.venv/Scripts/python.exe agent/api.py
```

服务固定默认监听 `127.0.0.1:8000`，按 Ctrl+C 停止。另开一个 PowerShell 终端调用：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/status | ConvertTo-Json -Depth 10
```

也可以用浏览器打开 `http://127.0.0.1:8000/api/status` 查看 JSON，
打开 `http://127.0.0.1:8000/docs` 查看交互式接口文档。

### Ubuntu / Linux 启动和调用

```bash
cd /path/to/vibe-coding-learning
./agent/.venv/bin/python -m pip install -r agent/requirements.txt
./agent/.venv/bin/python agent/api.py
```

另开本机终端调用（如果已有 curl）：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/status
```

没有 curl 时可使用 Python 标准库：

```bash
./agent/.venv/bin/python -c "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8000/api/status').read().decode())"
```

也支持从项目根目录直接使用 Uvicorn，显式指定本机地址及单进程：

```bash
./agent/.venv/bin/python -m uvicorn agent.api:app --host 127.0.0.1 --port 8000 --workers 1
```

### 接口行为

| 路径 | 返回 |
| --- | --- |
| `GET /health` | HTTP 200，`{"status":"ok"}`，仅表示 HTTP 服务存活 |
| `GET /api/status` | HTTP 200，包含 `timestamp`、`errors`、`cpu`、`memory`、`disk`、`network`、`system`，结构与 CLI 相同 |

`/api/status` 每次请求实时调用现有 `Collector.collect()`，没有后台 30 秒采集任务。
CPU 采样约耗时 0.2 秒，网络速率为两次成功网络读取之间的平均值。
服务启动时建立网络基线；新接口或预采样失败时，首个有效读取的速率可能为 `null`。
采集器在同一进程内复用，锁保护并发请求的基线，采集请求串行执行；健康检查独立响应。
使用单进程即可，不需要多 worker。每次服务重启都会重建基线。
指标失败时对应字段为 `null`，`errors` 含错误说明，并记录日志；其他指标继续返回，下一次请求重试。
因此 `/health` 正常不代表每个指标都正常，请结合 `/api/status.errors` 检查。

CLI 的 `--once`、`--interval` 和 JSON Lines 输出保持原行为。
这版不提供跨域配置或鉴权，不修改 Dashboard，也不配置 systemd、nginx 或防火墙。
所有启动示例仅监听本机，不开放公网。

参考：[psutil 官方文档](https://psutil.readthedocs.io/stable/)、
[FastAPI 测试文档](https://fastapi.tiangolo.com/tutorial/testing/)、
[Uvicorn 设置文档](https://www.uvicorn.org/settings/)。
