"""本地 API：复用现有采集器，允许本机 8080 端口的静态 Dashboard。"""
from contextlib import asynccontextmanager
import logging
from threading import Lock
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import uvicorn
"""本地 HTTP API，复用 monitor.py 的指标采集。"""




# 同时支持 python agent/api.py 和 uvicorn agent.api:app。
if __package__:
    from . import monitor
else:
    import monitor


@asynccontextmanager
async def lifespan(app):
    if monitor.psutil is None:
        raise RuntimeError("缺少 psutil，请安装 agent/requirements.txt")
    app.state.collector = monitor.Collector()
    app.state.collection_lock = Lock()
    try:
        app.state.collector.collect_network()
    except Exception:
        LOGGER.exception("网络预采样失败，将在 API 请求中重试")
    try:
        yield
    finally:
        del app.state.collector
        del app.state.collection_lock


app = FastAPI(title="服务器监控 Agent", lifespan=lifespan)


@app.get("/health")
def health():
    # 存活检查独立于采集，指标异常请查看 /api/status 的 errors。
    return {"status": "ok"}


@app.get("/api/status")
def status(request: Request):
    # 同步路由由 FastAPI 在线程池执行，CPU 采样不阻塞事件循环。
    # 同一个 Collector 的读取串行执行，保护网络计数与时间基线。
    with request.app.state.collection_lock:
        return request.app.state.collector.collect()


def main():
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
