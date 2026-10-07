"""本地 API：复用现有采集器，允许本机 8080 端口的静态 Dashboard。"""
from contextlib import asynccontextmanager
import logging
from threading import Lock
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

if __package__:
    from . import monitor
else:
    import monitor


@asynccontextmanager
async def lifespan(app):
    if monitor.psutil is None:
        raise RuntimeError("请先安装 agent/requirements.txt")
    app.state.collector = monitor.Collector()
    app.state.lock = Lock()
    try:
        app.state.collector.collect_network()
    except Exception:
        logging.exception("网络预采样失败，将在正式采集中重试")
    yield


app = FastAPI(title="服务器监控 Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_methods=["GET"],
    allow_headers=[],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def status(request: Request):
    # 同步路由在线程池执行，用锁保护网络速率基线。
    with request.app.state.lock:
        return request.app.state.collector.collect()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
