import asyncio
import json
from datetime import datetime, timedelta

import httpx

from . import bot, db
from .pipeline import sweep_buffers, sweep_reminders


def build_daily_content(biz_date):
    day = biz_date.strftime("%Y-%m-%d")
    created = db.query_one("SELECT COUNT(*) AS c FROM cards WHERE created_at LIKE ?", (day + "%",))["c"]
    confirmed = db.query_one("SELECT COUNT(*) AS c FROM cards WHERE confirmed_at LIKE ?", (day + "%",))["c"]
    pending = db.query_one("SELECT COUNT(*) AS c FROM cards WHERE status='pending'")["c"]
    reqs = db.query(
        """SELECT r.req_no, r.title, r.urgency, m.name AS module_name FROM requirements r
           LEFT JOIN modules m ON m.id=r.module_id
           WHERE r.created_at LIKE ? ORDER BY r.id DESC LIMIT 20""",
        (day + "%",),
    )
    lines = ["【需求日报 %s】" % day, "当日新增上报：%d 条；确认入池：%d 条；待确认存量：%d 条" % (created, confirmed, pending)]
    if reqs:
        lines.append("当日入池需求：")
        for r in reqs:
            lines.append("- %s %s（%s｜紧急度 %s）" % (r["req_no"], r["title"], r["module_name"] or "未分配模块", r["urgency"] or "中"))
    else:
        lines.append("当日无新入池需求。")
    return "\n".join(lines)


def build_weekly_content(biz_date):
    start = (biz_date - timedelta(days=6)).strftime("%Y-%m-%d")
    end = biz_date.strftime("%Y-%m-%d")
    reqs = db.query(
        """SELECT r.*, m.name AS module_name FROM requirements r
           LEFT JOIN modules m ON m.id=r.module_id
           WHERE r.created_at >= ? AND r.created_at <= ? ORDER BY r.id DESC""",
        (start + " 00:00:00", end + " 23:59:59"),
    )
    top = db.query(
        "SELECT req_no,title,freq FROM requirements ORDER BY freq DESC, updated_at DESC LIMIT 5"
    )
    trans = {s: 0 for s in ("assessing", "scheduled", "released")}
    for row in db.query(
        "SELECT to_status, COUNT(*) AS c FROM transitions WHERE created_at >= ? AND created_at <= ? GROUP BY to_status",
        (start + " 00:00:00", end + " 23:59:59"),
    ):
        if row["to_status"] in trans:
            trans[row["to_status"]] = row["c"]
    lines = ["【需求周报 %s ~ %s】" % (start, end)]
    if reqs:
        grouped = {}
        for r in reqs:
            grouped.setdefault(r["module_name"] or "未分配模块", []).append(r)
        lines.append("本周入池 %d 条，按模块分布：" % len(reqs))
        for name, items in grouped.items():
            lines.append("- %s（%d 条）：%s" % (name, len(items), "；".join(i["title"] for i in items[:5])))
    else:
        lines.append("本周期无新增需求。")
    if top:
        lines.append("提出次数 Top5：")
        for i, r in enumerate(top, 1):
            lines.append("%d. %s %s（%d 次）" % (i, r["req_no"], r["title"], r["freq"]))
    lines.append("状态流转：评估中 %d，已排期 %d，已上线 %d" % (trans["assessing"], trans["scheduled"], trans["released"]))
    return "\n".join(lines)


def push_broadcast(btype, biz_date=None):
    biz_date = biz_date or datetime.now()
    content = build_daily_content(biz_date) if btype == "daily" else build_weekly_content(biz_date)
    webhooks = [w.strip() for w in db.get_config("broadcast_webhooks", "").split(",") if w.strip()]
    status = "success"
    error = ""
    for url in webhooks:
        try:
            resp = httpx.post(url, json={"msgtype": "markdown", "markdown": {"content": content}}, timeout=10)
            if resp.status_code != 200:
                status = "failed"
                error = "HTTP %d" % resp.status_code
        except Exception as exc:
            status = "failed"
            error = str(exc)
    if not webhooks:
        status = "no_webhook"
    now = db.now()
    bid = db.execute(
        "INSERT INTO broadcasts(btype,biz_date,content,status,pushed_at,created_at) VALUES(?,?,?,?,?,?)",
        (btype, biz_date.strftime("%Y-%m-%d"), content, status, now if webhooks else None, now),
    )
    bot.send_group_message("需求播报", content)
    if status == "failed":
        _record_push_failure(error)
    else:
        db.set_config("broadcast_fail_count", "0")
    return {"id": bid, "status": status, "content": content}


def _record_push_failure(error):
    count = int(db.get_config("broadcast_fail_count", "0")) + 1
    db.set_config("broadcast_fail_count", str(count))
    if count >= 3:
        admins = db.query("SELECT name FROM users WHERE role='admin'")
        for admin in admins:
            bot.send_user_message(admin["name"], "需求播报连续 %d 次推送失败，请检查群机器人 Webhook 配置。最近错误：%s" % (count, error))


async def scheduler_loop():
    sent_marks = set()
    while True:
        try:
            sweep_buffers()
            sweep_reminders()
            now = datetime.now()
            hm = now.strftime("%H:%M")
            if db.get_config("broadcast_daily_time", "18:00") == hm:
                mark = "daily:" + now.strftime("%Y-%m-%d")
                if mark not in sent_marks:
                    sent_marks.add(mark)
                    push_broadcast("daily", now)
            weekly_day = int(db.get_config("broadcast_weekly_day", "5"))
            if now.isoweekday() == weekly_day and db.get_config("broadcast_weekly_time", "18:00") == hm:
                mark = "weekly:" + now.strftime("%Y-%W")
                if mark not in sent_marks:
                    sent_marks.add(mark)
                    push_broadcast("weekly", now)
        except Exception:
            pass
        await asyncio.sleep(15)
