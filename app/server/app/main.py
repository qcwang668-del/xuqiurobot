import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import bot, db
from .broadcast import scheduler_loop
from .routers_admin import router as admin_router
from .routers_core import router as core_router

app = FastAPI(title="需求搜集智能工作台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(core_router)
app.include_router(admin_router)


@app.on_event("startup")
def startup():
    db.init_db()


@app.on_event("startup")
async def start_scheduler():
    asyncio.create_task(scheduler_loop())


@app.on_event("startup")
async def start_bot_adapter():
    if db.get_config("bot_mode", "mock") != "wecom":
        return
    bot_id = db.get_config("bot_id")
    secret = db.get_config("bot_secret")
    if not bot_id or not secret:
        print("[bot] 当前为 wecom 模式但未配置 Bot ID/Secret，适配器未启动")
        return
    try:
        adapter = bot.WeComBotAdapter(bot_id, secret, asyncio.get_running_loop())
        bot.register_adapter(adapter)
        asyncio.create_task(adapter.start())
        print("[bot] 企微长连接适配器已启动")
    except Exception as exc:
        print("[bot] 企微长连接适配器启动失败:", exc)


web_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if web_dist.exists():
    assets_dir = web_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        target = web_dist / full_path if full_path else None
        if target and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(web_dist / "index.html"))
