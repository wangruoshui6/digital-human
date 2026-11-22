import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.auth import ensure_default_admin, get_current_admin
from app.database import Base, engine
from app.routers import auth, avatar, dashboard, knowledge, report

Base.metadata.create_all(bind=engine)

# 首次启动自动生成默认管理员（用户名 admin，随机密码打印到控制台）
ensure_default_admin()

app = FastAPI(title="Scenic Admin")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 登录接口本身不鉴权；其余管理接口统一要求 Bearer Token
app.include_router(auth.router)
app.include_router(avatar.router, dependencies=[Depends(get_current_admin)])
app.include_router(dashboard.router, dependencies=[Depends(get_current_admin)])
app.include_router(knowledge.router, dependencies=[Depends(get_current_admin)])
app.include_router(report.router, dependencies=[Depends(get_current_admin)])


# ── LiveTalking 代理 ──
# 说明：/lt/* 是 WebRTC 信令与推流代理，游客端也会用到，故不做管理员鉴权。
import httpx

LT_BASE = "http://127.0.0.1:8010"


@app.api_route("/lt/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def proxy_lt(request: Request, path: str):
    url = f"{LT_BASE}/{path}"
    qs = str(request.url.query)
    if qs:
        url += "?" + qs
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.request(request.method, url, headers=headers, content=body or None)
    except httpx.RequestError as exc:
        # LiveTalking 未启动/不可达时，返回结构化 JSON 而不是纯文本 500，
        # 让前端能显示可读提示（否则 r.json() 会报 "Unexpected token"）
        return JSONResponse(
            status_code=502,
            content={
                "error": "LiveTalking 服务不可达",
                "detail": f"{exc.__class__.__name__}: {exc}",
                "hint": "请先启动 third_party/LiveTalking（py -3.12 app.py --listenport 8010），并确认 8010 端口已监听",
            },
        )
    return Response(content=r.content, status_code=r.status_code, headers=dict(r.headers))


@app.get("/api/health")
def health():
    return {"status": "ok"}


frontend = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend.exists():
    app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8012)
