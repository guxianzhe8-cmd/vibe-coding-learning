# vibe-coding-learning
my first vibe-coding-learning
## My Learning Journey

This is my first Git project.

I am learning Git, GitHub and Vibe Coding.

## Goals

- Learn Git
- Learn AI Coding
- Build my first application
## Dashboard 接入真实 Agent API

页面保留原有设计，展示当前 Agent 所在的一台主机。加载页面和点击刷新时会调用
`GET /api/status`，显示 CPU、内存、磁盘及每个接口的上传/下载速率和累计字节数。
单项采集失败显示“暂无数据”及错误说明；API 访问失败会清空读数并提示重试。
这里“在线”表示 API 可达，不代表所有指标采集正常。

### Windows 本地测试

在项目根目录打开两个 PowerShell 终端。

终端一启动 API（如果已有虚拟环境，无需再次创建）：

```powershell
cd D:\Projects\vibe-coding-learning
python -m venv agent/.venv
& ./agent/.venv/Scripts/python.exe -m pip install -r agent/requirements.txt
& ./agent/.venv/Scripts/python.exe agent/api.py
```

终端二启动静态页面：

```powershell
cd D:\Projects\vibe-coding-learning
python -m http.server 8080 --bind 127.0.0.1
```

在浏览器打开 http://localhost:8080 ，不要直接双击 HTML。
点击刷新验证数据更新；停止 API 后再次刷新，应显示访问失败；重新启动 API 后点击刷新应恢复。
两个服务都可使用 Ctrl+C 停止。静态服务器只用于本地开发，服务目录包含项目源码。

### Ubuntu / Linux 本地测试

终端一：

```bash
cd /path/to/vibe-coding-learning
python3 -m venv agent/.venv
./agent/.venv/bin/python -m pip install -r agent/requirements.txt
./agent/.venv/bin/python agent/api.py
```

终端二：

```bash
cd /path/to/vibe-coding-learning
python3 -m http.server 8080 --bind 127.0.0.1
```

在同一台电脑的浏览器中打开 http://localhost:8080 。这不会开放公网或自动部署。

### API 地址配置

修改 `config.js` 中的 `apiBaseUrl`，默认 `http://localhost:8000`，没有写死服务器 IP。
若静态页面和 API 经同源代理提供，可设置为 `""`，请求将使用相对路径 `/api/status`。
`timeoutMs` 为请求超时时间，默认 10 秒。修改后刷新浏览器。

本地页面端口 8080 和 API 端口 8000 属于不同来源，因此 API 仅允许
`http://localhost:8080` 和 `http://127.0.0.1:8080` 的 GET 跨域访问。
如果修改页面端口或域名，需要同步修改 `agent/api.py` 的 `allow_origins`。
前端配置不会改变 API 的监听地址；API 默认仍仅监听 `127.0.0.1:8000`。
Agent 不返回主机 IP，因此卡片显示配置的 API 地址，不编造服务器 IP。

`style.css` 保持原样；`index.html` 只更新模式文案、计数和配置脚本引用。
根目录 README 原有学习记录保留。CLI 仍可使用 `agent/monitor.py --once` / `--interval`。
