from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import broadcast, bot as bot_module, db, pipeline, security, wecom_api
from .deps import current_user, require_roles

router = APIRouter(prefix="/api")

admin_only = require_roles("admin")


def _mask_secret(value):
    if not value:
        return ""
    return "****" + value[-4:] if len(value) > 4 else "****"


@router.get("/admin/model-config")
def get_model_config(user=Depends(admin_only)):
    cfg = db.get_configs()
    return {
        "model_base_url": cfg.get("model_base_url", ""),
        "model_name": cfg.get("model_name", ""),
        "model_timeout": cfg.get("model_timeout", "30"),
        "similarity_threshold": cfg.get("similarity_threshold", "0.85"),
        "api_key_masked": _mask_secret(cfg.get("model_api_key", "")),
        "api_key_set": bool(cfg.get("model_api_key")),
    }


class ModelConfigBody(BaseModel):
    model_base_url: str
    model_name: str
    model_timeout: str = "30"
    similarity_threshold: str = "0.85"
    api_key: str = ""


@router.put("/admin/model-config")
def put_model_config(body: ModelConfigBody, user=Depends(admin_only)):
    db.set_config("model_base_url", body.model_base_url.strip())
    db.set_config("model_name", body.model_name.strip())
    db.set_config("model_timeout", body.model_timeout.strip() or "30")
    db.set_config("similarity_threshold", body.similarity_threshold.strip() or "0.85")
    if body.api_key.strip():
        db.set_config("model_api_key", body.api_key.strip())
    return {"ok": True}


@router.get("/admin/bot-config")
def get_bot_config(user=Depends(admin_only)):
    cfg = db.get_configs()
    return {
        "bot_id": cfg.get("bot_id", ""),
        "secret_masked": _mask_secret(cfg.get("bot_secret", "")),
        "secret_set": bool(cfg.get("bot_secret")),
        "wecom_corpid": cfg.get("wecom_corpid", ""),
        "contact_secret_masked": _mask_secret(cfg.get("wecom_contact_secret", "")),
        "contact_secret_set": bool(cfg.get("wecom_contact_secret")),
        "bot_mode": cfg.get("bot_mode", "mock"),
        "connected": bot_module.is_connected() if cfg.get("bot_mode") == "wecom" else True,
    }


class BotConfigBody(BaseModel):
    bot_id: str = ""
    bot_secret: str = ""
    bot_mode: str = "mock"
    wecom_corpid: str = ""
    wecom_contact_secret: str = ""


@router.put("/admin/bot-config")
def put_bot_config(body: BotConfigBody, user=Depends(admin_only)):
    db.set_config("bot_id", body.bot_id.strip())
    if body.bot_secret.strip():
        db.set_config("bot_secret", body.bot_secret.strip())
    db.set_config("wecom_corpid", body.wecom_corpid.strip())
    if body.wecom_contact_secret.strip():
        db.set_config("wecom_contact_secret", body.wecom_contact_secret.strip())
    db.set_config("bot_mode", body.bot_mode if body.bot_mode in ("mock", "wecom") else "mock")
    return {"ok": True}


@router.get("/admin/broadcast-config")
def get_broadcast_config(user=Depends(admin_only)):
    cfg = db.get_configs()
    return {
        "broadcast_daily_time": cfg.get("broadcast_daily_time", "18:00"),
        "broadcast_weekly_day": cfg.get("broadcast_weekly_day", "5"),
        "broadcast_weekly_time": cfg.get("broadcast_weekly_time", "18:00"),
        "broadcast_webhooks": cfg.get("broadcast_webhooks", ""),
        "last_status": (db.query_one("SELECT status,pushed_at FROM broadcasts ORDER BY id DESC LIMIT 1") or {}),
    }


class BroadcastConfigBody(BaseModel):
    broadcast_daily_time: str
    broadcast_weekly_day: str
    broadcast_weekly_time: str
    broadcast_webhooks: str = ""


@router.put("/admin/broadcast-config")
def put_broadcast_config(body: BroadcastConfigBody, user=Depends(admin_only)):
    db.set_config("broadcast_daily_time", body.broadcast_daily_time)
    db.set_config("broadcast_weekly_day", body.broadcast_weekly_day)
    db.set_config("broadcast_weekly_time", body.broadcast_weekly_time)
    db.set_config("broadcast_webhooks", body.broadcast_webhooks)
    return {"ok": True}


@router.get("/admin/members")
def list_members(user=Depends(admin_only)):
    return db.query("SELECT id,username,name,role,wecom_userid,created_at FROM users ORDER BY id")


class MemberBody(BaseModel):
    username: str
    name: str
    role: str = "member"
    password: str = ""
    wecom_userid: str = ""


@router.post("/admin/members")
def create_member(body: MemberBody, user=Depends(admin_only)):
    if db.query_one("SELECT id FROM users WHERE username=?", (body.username,)):
        raise HTTPException(status_code=400, detail="用户名已存在")
    if body.role not in ("member", "leader", "admin"):
        raise HTTPException(status_code=400, detail="角色不合法")
    uid = db.execute(
        "INSERT INTO users(username,password_hash,name,role,wecom_userid,created_at) VALUES(?,?,?,?,?,?)",
        (body.username, security.hash_password(body.password or "123456"), body.name, body.role, body.wecom_userid, db.now()),
    )
    return {"ok": True, "id": uid}


@router.put("/admin/members/{uid}")
def update_member(uid: int, body: MemberBody, user=Depends(admin_only)):
    target = db.query_one("SELECT * FROM users WHERE id=?", (uid,))
    if not target:
        raise HTTPException(status_code=404, detail="成员不存在")
    if target["username"] == "admin" and body.role != "admin":
        raise HTTPException(status_code=400, detail="内置管理员不可降权")
    db.execute("UPDATE users SET name=?, role=?, wecom_userid=? WHERE id=?", (body.name, body.role, body.wecom_userid, uid))
    if body.password:
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (security.hash_password(body.password), uid))
    return {"ok": True}


@router.get("/admin/contacts")
def list_contacts(user=Depends(admin_only)):
    rows = db.query("SELECT * FROM wecom_contacts ORDER BY first_seen DESC")
    bound = {r["wecom_userid"]: r["name"] for r in db.query("SELECT name,wecom_userid FROM users WHERE wecom_userid IS NOT NULL AND wecom_userid != ''")}
    for row in rows:
        row["member_name"] = bound.get(row["wecom_userid"], "")
    return rows


class ContactBody(BaseModel):
    name: str = ""


@router.put("/admin/contacts/{userid}")
def update_contact(userid: str, body: ContactBody, user=Depends(admin_only)):
    if not db.query_one("SELECT wecom_userid FROM wecom_contacts WHERE wecom_userid=?", (userid,)):
        raise HTTPException(status_code=404, detail="联系人不存在")
    db.execute("UPDATE wecom_contacts SET name=?, updated_at=? WHERE wecom_userid=?", (body.name.strip(), db.now(), userid))
    return {"ok": True}


@router.delete("/admin/contacts/{userid}")
def delete_contact(userid: str, user=Depends(admin_only)):
    db.execute("DELETE FROM wecom_contacts WHERE wecom_userid=?", (userid,))
    return {"ok": True}


@router.post("/admin/contacts/sync")
def sync_contacts(user=Depends(admin_only)):
    resolved, total = wecom_api.sync_contacts()
    return {"ok": True, "resolved": resolved, "total": total}


@router.get("/modules")
def list_modules(all: bool = False, user=Depends(current_user)):
    if all:
        return db.query("SELECT * FROM modules ORDER BY id")
    return db.query("SELECT * FROM modules WHERE status='启用' ORDER BY id")


class ModuleBody(BaseModel):
    name: str
    status: str = "启用"


@router.post("/admin/modules")
def create_module(body: ModuleBody, user=Depends(admin_only)):
    if db.query_one("SELECT id FROM modules WHERE name=?", (body.name,)):
        raise HTTPException(status_code=400, detail="模块已存在")
    return {"ok": True, "id": db.execute("INSERT INTO modules(name,status) VALUES(?,?)", (body.name, body.status))}


@router.put("/admin/modules/{mid}")
def update_module(mid: int, body: ModuleBody, user=Depends(admin_only)):
    if not db.query_one("SELECT id FROM modules WHERE id=?", (mid,)):
        raise HTTPException(status_code=404, detail="模块不存在")
    db.execute("UPDATE modules SET name=?, status=? WHERE id=?", (body.name, body.status, mid))
    return {"ok": True}


@router.get("/admin/masking-words")
def list_masking_words(user=Depends(admin_only)):
    return db.query("SELECT * FROM masking_words ORDER BY id")


class WordBody(BaseModel):
    word: str


@router.post("/admin/masking-words")
def create_masking_word(body: WordBody, user=Depends(admin_only)):
    if not body.word.strip():
        raise HTTPException(status_code=400, detail="词条不能为空")
    try:
        return {"ok": True, "id": db.execute("INSERT INTO masking_words(word) VALUES(?)", (body.word.strip(),))}
    except Exception:
        raise HTTPException(status_code=400, detail="词条已存在")


@router.delete("/admin/masking-words/{wid}")
def delete_masking_word(wid: int, user=Depends(admin_only)):
    db.execute("DELETE FROM masking_words WHERE id=?", (wid,))
    return {"ok": True}


@router.get("/admin/ai-logs")
def ai_logs(page: int = 1, size: int = 20, user=Depends(admin_only)):
    total = db.query_one("SELECT COUNT(*) AS c FROM ai_logs")["c"]
    rows = db.query("SELECT * FROM ai_logs ORDER BY id DESC LIMIT ? OFFSET ?", (size, (page - 1) * size))
    return {"total": total, "items": rows}


@router.get("/broadcasts")
def list_broadcasts(page: int = 1, size: int = 20, user=Depends(current_user)):
    total = db.query_one("SELECT COUNT(*) AS c FROM broadcasts")["c"]
    rows = db.query("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ? OFFSET ?", (size, (page - 1) * size))
    return {"total": total, "items": rows}


class GenerateBody(BaseModel):
    btype: str = "daily"


@router.post("/broadcasts/generate")
def generate_broadcast(body: GenerateBody, user=Depends(require_roles("leader", "admin"))):
    if body.btype not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="类型不合法")
    return broadcast.push_broadcast(body.btype)


@router.post("/broadcasts/{bid}/resend")
def resend_broadcast(bid: int, user=Depends(require_roles("leader", "admin"))):
    row = db.query_one("SELECT * FROM broadcasts WHERE id=?", (bid,))
    if not row:
        raise HTTPException(status_code=404, detail="播报不存在")
    import datetime as _dt
    biz = _dt.datetime.strptime(row["biz_date"], "%Y-%m-%d")
    return broadcast.push_broadcast(row["btype"], biz)


@router.get("/stats")
def stats(user=Depends(current_user)):
    trend = db.query(
        """SELECT substr(created_at,1,10) AS day, COUNT(*) AS c FROM cards
           WHERE created_at >= date('now','-13 day') GROUP BY day ORDER BY day"""
    )
    top_freq = db.query("SELECT req_no,title,freq FROM requirements ORDER BY freq DESC, updated_at DESC LIMIT 10")
    module_dist = db.query(
        """SELECT COALESCE(m.name,'未分配模块') AS name, COUNT(*) AS c FROM requirements r
           LEFT JOIN modules m ON m.id=r.module_id GROUP BY name ORDER BY c DESC"""
    )
    status_dist = db.query("SELECT status AS name, COUNT(*) AS c FROM requirements GROUP BY status")
    type_dist = db.query("SELECT req_type AS name, COUNT(*) AS c FROM requirements GROUP BY req_type")
    source_dist = db.query(
        "SELECT source_object AS name, COUNT(*) AS c FROM cards WHERE source_object != '' AND status='confirmed' GROUP BY source_object ORDER BY c DESC LIMIT 10"
    )
    return {"trend": trend, "top_freq": top_freq, "module_dist": module_dist,
            "status_dist": status_dist, "type_dist": type_dist, "source_dist": source_dist}


class SimulateBody(BaseModel):
    user: str = "王雁"
    text: str = ""
    msg_type: str = "text"


@router.post("/simulate/message")
def simulate_message(body: SimulateBody, user=Depends(current_user)):
    if body.msg_type != "text":
        pipeline.handle_non_text(body.user, body.msg_type)
    else:
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="消息内容不能为空")
        pipeline.handle_incoming(body.user, body.text)
    return {"ok": True}


@router.get("/simulate/messages")
def simulate_messages(user_name: str = "王雁", limit: int = 50, user=Depends(current_user)):
    rows = db.query(
        "SELECT * FROM bot_messages WHERE user=? ORDER BY id DESC LIMIT ?",
        (user_name, limit),
    )
    rows.reverse()
    return rows


@router.get("/meta")
def meta(user=Depends(current_user)):
    return {
        "req_types": ["新需求", "体验优化", "缺陷反馈"],
        "urgencies": ["高", "中", "低"],
        "statuses": pipeline.REQ_STATUS_LABELS,
        "members": [r["name"] for r in db.query("SELECT name FROM users ORDER BY id")],
        "bot_mode": db.get_config("bot_mode", "mock"),
    }
