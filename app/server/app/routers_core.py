import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import bot as bot_module, db, pipeline, security
from .deps import current_user, require_roles

router = APIRouter(prefix="/api")

SORTABLE_INBOX = {"created_at": "created_at", "confidence": "confidence"}
SORTABLE_REQ = {"created_at": "created_at", "updated_at": "updated_at", "freq": "freq"}


def _attach_display_names(rows):
    mapping = {
        r["wecom_userid"]: r["name"]
        for r in db.query("SELECT name,wecom_userid FROM users WHERE wecom_userid IS NOT NULL AND wecom_userid != ''")
    }
    contact_mapping = {
        r["wecom_userid"]: r["name"]
        for r in db.query("SELECT wecom_userid,name FROM wecom_contacts WHERE name != ''")
    }
    for row in rows:
        source = row.get("source_user")
        row["source_display"] = mapping.get(source) or contact_mapping.get(source) or source
    return rows


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginBody):
    user = db.query_one("SELECT * FROM users WHERE username=?", (body.username,))
    if not user or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token = security.make_token(user["id"], db.get_config("auth_secret"))
    return {"token": token, "user": {"id": user["id"], "username": user["username"], "name": user["name"], "role": user["role"]}}


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@router.get("/overview")
def overview(user=Depends(current_user)):
    today = db.today()
    return {
        "total": db.query_one("SELECT COUNT(*) AS c FROM requirements")["c"],
        "pending": db.query_one("SELECT COUNT(*) AS c FROM cards WHERE status='pending'")["c"],
        "my_pending": db.query_one("SELECT COUNT(*) AS c FROM cards WHERE status='pending' AND source_user=?", (user["name"],))["c"],
        "today_new": db.query_one("SELECT COUNT(*) AS c FROM cards WHERE created_at LIKE ?", (today + "%",))["c"],
        "today_confirmed": db.query_one("SELECT COUNT(*) AS c FROM requirements WHERE created_at LIKE ?", (today + "%",))["c"],
        "status_dist": db.query("SELECT status, COUNT(*) AS c FROM requirements GROUP BY status"),
        "latest_pending": db.query("SELECT id,title,req_type,urgency,confidence,source_user,created_at FROM cards WHERE status='pending' ORDER BY id DESC LIMIT 5"),
    }


@router.get("/inbox")
def inbox(status: str = "pending", keyword: str = "", req_type: str = "", urgency: str = "",
          confidence: str = "", source_user: str = "", date_from: str = "", date_to: str = "",
          sort: str = "created_at", order: str = "desc", page: int = 1, size: int = 20,
          user=Depends(current_user)):
    cond = ["status=?"]
    args = [status]
    if user["role"] == "member":
        cond.append("source_user=?")
        args.append(user["name"])
    if keyword:
        cond.append("(title LIKE ? OR description LIKE ?)")
        args += ["%" + keyword + "%", "%" + keyword + "%"]
    if req_type:
        cond.append("req_type=?")
        args.append(req_type)
    if urgency:
        cond.append("urgency=?")
        args.append(urgency)
    if confidence == "low":
        cond.append("confidence < 0.6")
    elif confidence == "mid":
        cond.append("confidence >= 0.6 AND confidence < 0.8")
    elif confidence == "high":
        cond.append("confidence >= 0.8")
    if source_user:
        cond.append("source_user=?")
        args.append(source_user)
    if date_from:
        cond.append("created_at >= ?")
        args.append(date_from + " 00:00:00")
    if date_to:
        cond.append("created_at <= ?")
        args.append(date_to + " 23:59:59")
    where = " AND ".join(cond)
    sort_col = SORTABLE_INBOX.get(sort, "created_at")
    direction = "ASC" if order == "asc" else "DESC"
    total = db.query_one("SELECT COUNT(*) AS c FROM cards WHERE " + where, args)["c"]
    rows = db.query(
        "SELECT * FROM cards WHERE " + where + " ORDER BY " + sort_col + " " + direction + " LIMIT ? OFFSET ?",
        args + [size, (page - 1) * size],
    )
    return {"total": total, "items": _attach_display_names(rows)}


@router.get("/inbox/{card_id}")
def inbox_detail(card_id: int, user=Depends(current_user)):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    if card.get("similar_requirement_id"):
        card["similar"] = db.query_one("SELECT id,req_no,title,status FROM requirements WHERE id=?", (card["similar_requirement_id"],))
    _attach_display_names([card])
    return card


class ConfirmBody(BaseModel):
    edits: dict | None = None
    decision: str | None = None


@router.post("/inbox/{card_id}/confirm")
def inbox_confirm(card_id: int, body: ConfirmBody, user=Depends(current_user)):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    if user["role"] == "member" and card["source_user"] != user["name"]:
        raise HTTPException(status_code=403, detail="仅可处理本人上报的卡片")
    result = pipeline.confirm_card(card_id, user["name"], edits=body.edits, decision=body.decision)
    if not result.get("ok") and not result.get("need_decision"):
        raise HTTPException(status_code=400, detail=result.get("message", "操作失败"))
    return result


@router.post("/inbox/{card_id}/ignore")
def inbox_ignore(card_id: int, user=Depends(current_user)):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    if user["role"] == "member" and card["source_user"] != user["name"]:
        raise HTTPException(status_code=403, detail="仅可处理本人上报的卡片")
    result = pipeline.ignore_card(card_id, user["name"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/inbox/{card_id}/resend")
def inbox_resend(card_id: int, user=Depends(current_user)):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    if card["status"] != "pending":
        raise HTTPException(status_code=400, detail="仅待确认卡片可重新推送")
    if user["role"] == "member" and card["source_user"] != user["name"]:
        raise HTTPException(status_code=403, detail="仅可处理本人上报的卡片")
    bot_module.send_card_message(card)
    return {"ok": True}


@router.post("/inbox/{card_id}/reextract")
def inbox_reextract(card_id: int, user=Depends(current_user)):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    if user["role"] == "member" and card["source_user"] != user["name"]:
        raise HTTPException(status_code=403, detail="仅可处理本人上报的卡片")
    result = pipeline.reextract_card(card_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


class BatchBody(BaseModel):
    ids: list[int]


@router.post("/inbox/batch-ignore")
def inbox_batch_ignore(body: BatchBody, user=Depends(current_user)):
    done = 0
    for cid in body.ids:
        card = db.query_one("SELECT * FROM cards WHERE id=?", (cid,))
        if card and card["status"] == "pending" and (user["role"] != "member" or card["source_user"] == user["name"]):
            pipeline.ignore_card(cid, user["name"])
            done += 1
    return {"ok": True, "count": done}


@router.post("/inbox/{card_id}/restore")
def inbox_restore(card_id: int, user=Depends(current_user)):
    result = pipeline.restore_card(card_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/requirements")
def requirements(keyword: str = "", module_id: int = 0, req_type: str = "", status: str = "",
                 urgency: str = "", source: str = "", created_by: str = "",
                 date_from: str = "", date_to: str = "", sort: str = "updated_at",
                 order: str = "desc", page: int = 1, size: int = 20, user=Depends(current_user)):
    cond = ["1=1"]
    args = []
    if keyword:
        cond.append("(r.title LIKE ? OR r.description LIKE ?)")
        args += ["%" + keyword + "%", "%" + keyword + "%"]
    if module_id:
        cond.append("r.module_id=?")
        args.append(module_id)
    if req_type:
        cond.append("r.req_type=?")
        args.append(req_type)
    if status:
        cond.append("r.status=?")
        args.append(status)
    if urgency:
        cond.append("r.urgency=?")
        args.append(urgency)
    if source:
        cond.append("r.source_objects LIKE ?")
        args.append("%" + source + "%")
    if created_by:
        cond.append("r.created_by=?")
        args.append(created_by)
    if date_from:
        cond.append("r.created_at >= ?")
        args.append(date_from + " 00:00:00")
    if date_to:
        cond.append("r.created_at <= ?")
        args.append(date_to + " 23:59:59")
    where = " AND ".join(cond)
    sort_col = SORTABLE_REQ.get(sort, "updated_at")
    direction = "ASC" if order == "asc" else "DESC"
    total = db.query_one("SELECT COUNT(*) AS c FROM requirements r WHERE " + where, args)["c"]
    rows = db.query(
        """SELECT r.*, m.name AS module_name FROM requirements r
           LEFT JOIN modules m ON m.id=r.module_id
           WHERE """ + where + " ORDER BY r." + sort_col + " " + direction + " LIMIT ? OFFSET ?",
        args + [size, (page - 1) * size],
    )
    for row in rows:
        try:
            row["source_objects"] = json.loads(row["source_objects"] or "[]")
        except json.JSONDecodeError:
            row["source_objects"] = []
    return {"total": total, "items": rows}


class RequirementBody(BaseModel):
    title: str
    description: str = ""
    module_id: int | None = None
    req_type: str = "新需求"
    urgency: str = "中"
    source_objects: list[str] = []
    expect_time: str = ""
    force: bool = False


@router.post("/requirements")
def create_requirement(body: RequirementBody, user=Depends(current_user)):
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="标题必填")
    dup = db.query_one("SELECT id,req_no,title FROM requirements WHERE title=?", (body.title.strip(),))
    if dup and not body.force:
        return {"ok": False, "dup": {"req_no": dup["req_no"], "title": dup["title"]}}
    now = db.now()
    req_no = pipeline._next_req_no()
    req_id = db.execute(
        """INSERT INTO requirements(req_no,title,description,module_id,req_type,urgency,source_objects,
           expect_time,status,freq,created_by,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,'confirmed',1,?,?,?)""",
        (req_no, body.title.strip(), body.description, body.module_id, body.req_type, body.urgency,
         json.dumps(body.source_objects, ensure_ascii=False), body.expect_time, user["name"], now, now),
    )
    db.execute(
        "INSERT INTO transitions(requirement_id,from_status,to_status,operator,reason,created_at) VALUES(?,?,?,?,?,?)",
        (req_id, None, "confirmed", user["name"], "手工补录", now),
    )
    return {"ok": True, "id": req_id, "req_no": req_no}


@router.get("/requirements/export")
def export_requirements(keyword: str = "", module_id: int = 0, req_type: str = "", status: str = "",
                        urgency: str = "", user=Depends(current_user)):
    data = requirements(keyword, module_id, req_type, status, urgency, "", "", "", "", "updated_at", "desc", 1, 10000, user)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["需求编号", "标题", "描述", "所属模块", "类型", "紧急度", "状态", "来源", "期望时间", "提出次数", "创建人", "创建时间", "更新时间"])
    labels = pipeline.REQ_STATUS_LABELS
    for r in data["items"]:
        writer.writerow([r["req_no"], r["title"], r["description"], r["module_name"] or "", r["req_type"], r["urgency"],
                         labels.get(r["status"], r["status"]), "、".join(r["source_objects"]), r["expect_time"],
                         r["freq"], r["created_by"], r["created_at"], r["updated_at"]])
    content = "﻿" + buf.getvalue()
    return StreamingResponse(iter([content.encode("utf-8-sig")]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=requirements.csv"})


@router.get("/requirements/{req_id}")
def requirement_detail(req_id: int, user=Depends(current_user)):
    req = db.query_one(
        """SELECT r.*, m.name AS module_name FROM requirements r
           LEFT JOIN modules m ON m.id=r.module_id WHERE r.id=?""",
        (req_id,),
    )
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    try:
        req["source_objects"] = json.loads(req["source_objects"] or "[]")
    except json.JSONDecodeError:
        req["source_objects"] = []
    req["evidences"] = _attach_display_names(db.query("SELECT * FROM evidences WHERE requirement_id=? ORDER BY id", (req_id,)))
    req["transitions"] = db.query("SELECT * FROM transitions WHERE requirement_id=? ORDER BY id", (req_id,))
    return req


@router.put("/requirements/{req_id}")
def update_requirement(req_id: int, body: RequirementBody, user=Depends(current_user)):
    req = db.query_one("SELECT * FROM requirements WHERE id=?", (req_id,))
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="标题必填")
    db.execute(
        """UPDATE requirements SET title=?, description=?, module_id=?, req_type=?, urgency=?,
           source_objects=?, expect_time=?, updated_at=? WHERE id=?""",
        (body.title.strip(), body.description, body.module_id, body.req_type, body.urgency,
         json.dumps(body.source_objects, ensure_ascii=False), body.expect_time, db.now(), req_id),
    )
    db.execute(
        "INSERT INTO transitions(requirement_id,from_status,to_status,operator,reason,created_at) VALUES(?,?,?,?,?,?)",
        (req_id, req["status"], req["status"], user["name"], "编辑需求", db.now()),
    )
    return {"ok": True}


@router.delete("/requirements/{req_id}")
def delete_requirement(req_id: int, user=Depends(require_roles("leader", "admin"))):
    if not db.query_one("SELECT id FROM requirements WHERE id=?", (req_id,)):
        raise HTTPException(status_code=404, detail="需求不存在")
    db.execute("DELETE FROM evidences WHERE requirement_id=?", (req_id,))
    db.execute("DELETE FROM transitions WHERE requirement_id=?", (req_id,))
    db.execute("DELETE FROM requirements WHERE id=?", (req_id,))
    return {"ok": True}


class TransitionBody(BaseModel):
    to_status: str
    reason: str = ""


@router.post("/requirements/{req_id}/transition")
def transition_requirement(req_id: int, body: TransitionBody, user=Depends(require_roles("leader", "admin"))):
    req = db.query_one("SELECT * FROM requirements WHERE id=?", (req_id,))
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    allowed = {"confirmed": ["assessing", "rejected"], "assessing": ["scheduled", "rejected"],
               "scheduled": ["released", "rejected"], "released": [], "rejected": []}
    if body.to_status not in allowed.get(req["status"], []):
        raise HTTPException(status_code=400, detail="当前状态不允许流转到目标状态")
    if body.to_status == "rejected" and not body.reason.strip():
        raise HTTPException(status_code=400, detail="流转为已拒绝必须填写拒绝原因")
    db.execute("UPDATE requirements SET status=?, reject_reason=?, updated_at=? WHERE id=?",
               (body.to_status, body.reason if body.to_status == "rejected" else req["reject_reason"], db.now(), req_id))
    db.execute(
        "INSERT INTO transitions(requirement_id,from_status,to_status,operator,reason,created_at) VALUES(?,?,?,?,?,?)",
        (req_id, req["status"], body.to_status, user["name"], body.reason, db.now()),
    )
    if body.to_status == "released":
        req = db.query_one("SELECT * FROM requirements WHERE id=?", (req_id,))
        pipeline.notify_released(req)
    elif body.to_status == "rejected":
        req = db.query_one("SELECT * FROM requirements WHERE id=?", (req_id,))
        pipeline.notify_rejected(req)
    return {"ok": True}
