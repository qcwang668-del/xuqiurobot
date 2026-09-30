import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from . import bot, db, llm, masking
from .config import DATA_DIR
from .similarity import find_similar

CONFIRM_WORDS = {"确认", "确认入池", "确定", "ok", "OK"}
IGNORE_WORDS = {"忽略"}
MERGE_WORDS = {"合并"}
NEW_WORDS = {"新建", "仍新建"}
HELP_WORDS = {"帮助", "?", "？", "help"}
MODIFY_PREFIXES = ("修改：", "修改:")

REQ_STATUS_LABELS = {
    "confirmed": "已确认",
    "assessing": "评估中",
    "scheduled": "已排期",
    "developing": "开发中",
    "released": "已上线",
    "rejected": "已拒绝",
}


def _parse_time(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def handle_non_text(user, msg_type):
    db.log_bot_message("in", user, msg_type, "<非文本消息>")
    bot.send_user_message(user, "暂不支持该类型消息，请以文字描述需求，可附带图片或 Word/PDF/Excel 附件。")


UPLOAD_DIR = Path(DATA_DIR) / "uploads"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
DOC_EXTS = {".docx", ".pdf", ".xlsx", ".xls", ".csv", ".txt", ".md"}
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024
MAX_ATTACHMENTS = 10


def _validate_attachment(filename, data):
    ext = _attachment_ext(filename)
    if ext not in IMAGE_EXTS | DOC_EXTS:
        return None, "不支持的附件格式 %s，支持图片及 Word/PDF/Excel/CSV/TXT。" % (ext or "未知")
    if not data:
        return None, "附件内容为空"
    if len(data) > MAX_ATTACHMENT_SIZE:
        return None, "附件超过 20MB 大小限制"
    return ext, ""


def _store_attachment_file(filename, data):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'[\\/:*?"<>|\r\n]', "_", filename)
    stored_name = "%s_%s" % (uuid.uuid4().hex[:12], safe_name)
    (UPLOAD_DIR / stored_name).write_bytes(data)
    return stored_name


def save_requirement_attachment(user, req_id, filename, data):
    """需求详情页手动新增附件，归属到需求。返回 (ok, message)。"""
    req = db.query_one("SELECT id FROM requirements WHERE id=?", (req_id,))
    if not req:
        return False, "需求不存在"
    ext, err = _validate_attachment(filename, data)
    if err:
        return False, err
    count = db.query_one(
        """SELECT COUNT(*) AS c FROM attachments
           WHERE requirement_id=? OR (requirement_id IS NULL AND card_id IN
             (SELECT card_id FROM evidences WHERE requirement_id=? AND card_id IS NOT NULL))""",
        (req_id, req_id),
    )["c"]
    if count >= MAX_ATTACHMENTS:
        return False, "附件数量已达 %d 个上限" % MAX_ATTACHMENTS
    msg_type = "image" if ext in IMAGE_EXTS else "file"
    stored_name = _store_attachment_file(filename, data)
    db.save_attachment(user, msg_type, filename, stored_name, len(data), requirement_id=req_id)
    return True, "附件已添加"


def save_card_attachment(user, card_id, filename, data):
    """卡片详情页手动新增附件，归属到卡片。返回 (ok, message)。"""
    card = db.query_one("SELECT id FROM cards WHERE id=?", (card_id,))
    if not card:
        return False, "卡片不存在"
    ext, err = _validate_attachment(filename, data)
    if err:
        return False, err
    count = db.query_one("SELECT COUNT(*) AS c FROM attachments WHERE card_id=?", (card_id,))["c"]
    if count >= MAX_ATTACHMENTS:
        return False, "附件数量已达 %d 个上限" % MAX_ATTACHMENTS
    msg_type = "image" if ext in IMAGE_EXTS else "file"
    stored_name = _store_attachment_file(filename, data)
    db.save_attachment(user, msg_type, filename, stored_name, len(data), card_id=card_id)
    return True, "附件已添加"


def _attachment_ext(filename):
    name = (filename or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot >= 0 else ""


def handle_attachment(user, msg_type, filename, data, source="mock", chat_id=None):
    """附件（图片/文档/表格）只做存储与卡片关联，不做内容解析。返回 (ok, message)。"""
    if source == "wecom":
        user = bot.maybe_resolve_sender(user)
    card = db.query_one(
        "SELECT * FROM cards WHERE source_user=? AND status='pending' ORDER BY id DESC LIMIT 1",
        (user,),
    )
    if msg_type == "image" and _attachment_ext(filename) not in IMAGE_EXTS:
        filename = (filename or "图片") + ".jpg"
    if not filename:
        filename = ("图片" if msg_type == "image" else "附件") + "_" + db.now().replace(" ", "_").replace(":", "")
    ext, err = _validate_attachment(filename, data)
    if err:
        bot.send_user_message(user, err, chat_id=chat_id)
        return False, err
    if card:
        count = db.query_one("SELECT COUNT(*) AS c FROM attachments WHERE card_id=?", (card["id"],))["c"]
    else:
        count = db.query_one("SELECT COUNT(*) AS c FROM attachments WHERE card_id IS NULL AND user=?", (user,))["c"]
    if count >= MAX_ATTACHMENTS:
        bot.send_user_message(user, "附件数量已达 %d 个上限，无法继续添加《%s》。" % (MAX_ATTACHMENTS, filename), chat_id=chat_id)
        return False, "附件数量已达上限"
    stored_name = _store_attachment_file(filename, data)
    att_id = db.save_attachment(user, msg_type, filename, stored_name, len(data), card_id=card["id"] if card else None)
    db.log_bot_message("in", user, msg_type, "【附件】%s" % filename)
    if card:
        bot.send_user_message(user, "已收到附件《%s》，已关联到您的需求卡片 #%d。" % (filename, card["id"]), chat_id=chat_id)
        return True, "已关联卡片 #%d" % card["id"]
    buf = db.query_one("SELECT * FROM buffers WHERE user=? AND processed=0 ORDER BY id DESC LIMIT 1", (user,))
    if buf:
        bot.send_user_message(user, "已收到附件《%s》，将随您本次提交的需求一并入池。" % filename, chat_id=chat_id)
    else:
        bot.send_user_message(user, "已收到附件《%s》，请再补充一段文字描述您的需求，附件将随需求一并提交。" % filename, chat_id=chat_id)
    return True, "附件已保存"


def handle_incoming(user, text, source="mock", chat_id=None):
    text = (text or "").strip()
    if not text:
        return
    if source == "wecom":
        user = bot.maybe_resolve_sender(user)
    db.log_bot_message("in", user, "text", text)
    if text in HELP_WORDS:
        bot.send_user_message(user, bot.HELP_TEXT)
        return
    card = db.query_one(
        "SELECT * FROM cards WHERE source_user=? AND status='pending' ORDER BY id DESC LIMIT 1",
        (user,),
    )
    if card:
        is_command = (
            text in CONFIRM_WORDS or text in IGNORE_WORDS or text in MERGE_WORDS or text in NEW_WORDS
            or any(text.startswith(prefix) for prefix in MODIFY_PREFIXES)
        )
        if is_command:
            bot.send_user_message(
                user,
                "需求确认已迁移至网页端，请在「需求搜集智能工作台 → 待确认收件箱」中处理您的需求卡片 #%d，处理结果会私信通知您。" % card["id"],
                chat_id=chat_id,
            )
            return
    _add_to_buffer(user, text, chat_id)
    bot.send_user_message(user, "已收到，正在整理分析，稍后同步您需求确认结果。", chat_id=chat_id)


def _add_to_buffer(user, text, chat_id=None):
    now = db.now()
    buf = db.query_one("SELECT * FROM buffers WHERE user=? AND processed=0 ORDER BY id DESC LIMIT 1", (user,))
    window = int(db.get_config("merge_window_seconds", "300"))
    if buf and (datetime.now() - _parse_time(buf["first_at"])).total_seconds() <= window:
        db.execute("UPDATE buffers SET text=text||?, last_at=?, chat_id=COALESCE(?, chat_id) WHERE id=?",
                   ("\n" + text, now, chat_id, buf["id"]))
    else:
        if buf:
            finalize_buffer(buf)
        db.execute("INSERT INTO buffers(user,text,first_at,last_at,chat_id,processed) VALUES(?,?,?,?,?,0)",
                   (user, text, now, now, chat_id))


def sweep_buffers():
    idle = int(db.get_config("buffer_idle_seconds", "10"))
    window = int(db.get_config("merge_window_seconds", "300"))
    rows = db.query("SELECT * FROM buffers WHERE processed=0")
    now_dt = datetime.now()
    for buf in rows:
        idle_sec = (now_dt - _parse_time(buf["last_at"])).total_seconds()
        age_sec = (now_dt - _parse_time(buf["first_at"])).total_seconds()
        if idle_sec >= idle or age_sec >= window:
            finalize_buffer(buf)


def finalize_buffer(buf):
    db.execute("UPDATE buffers SET processed=1 WHERE id=?", (buf["id"],))
    user, raw = buf["user"], buf["text"]
    words = [r["word"] for r in db.query("SELECT word FROM masking_words")]
    masked = masking.mask_text(raw, words)
    now = db.now()
    card_id = db.execute(
        """INSERT INTO cards(source_user,raw_text,masked_text,status,chat_id,created_at,updated_at)
           VALUES(?,?,?,'pending',?,?,?)""",
        (user, raw, masked, buf.get("chat_id"), now, now),
    )
    db.execute("UPDATE attachments SET card_id=? WHERE card_id IS NULL AND user=?", (card_id, user))
    try:
        result = llm.extract(masked, card_id=card_id)
    except llm.LLMError:
        result = None
    if result is None:
        db.execute(
            "UPDATE cards SET title=?, description=?, confidence=0, updated_at=? WHERE id=?",
            ("【待人工提炼】" + masked[:20], masked[:480], db.now(), card_id),
        )
        bot.send_user_message(user, "需求分析暂时失败，已保留原始内容并生成待人工提炼卡片，请前往网页端待确认收件箱处理。", chat_id=buf.get("chat_id"))
        return
    if result.get("intent") == "纯咨询闲聊":
        db.execute("UPDATE cards SET status='ignored', updated_at=? WHERE id=?", (db.now(), card_id))
        bot.send_user_message(user, "未识别到明确的需求信息，如需提报需求，请描述具体场景与期望效果。")
        return
    _apply_extract_result(card_id, masked, result)


def _apply_extract_result(card_id, fallback_text, result):
    db.execute(
        """UPDATE cards SET title=?, description=?, req_type=?, source_object=?, expect_time=?,
           urgency=?, confidence=?, updated_at=? WHERE id=?""",
        (
            (result.get("title") or "")[:30] or fallback_text[:28],
            (result.get("description") or "")[:500],
            result.get("intent") or "新需求",
            result.get("source_object") or "",
            result.get("expect_time") or "",
            result.get("urgency") or "中",
            float(result.get("confidence") or 0),
            db.now(),
            card_id,
        ),
    )


def reextract_card(card_id):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card or card["status"] != "pending":
        return {"ok": False, "message": "卡片不存在或已处理"}
    text = card["masked_text"] or card["raw_text"] or ""
    try:
        result = llm.extract(text, card_id=card_id)
    except llm.LLMError:
        return {"ok": False, "message": "大模型提炼失败，请稍后重试或人工编辑"}
    if result.get("intent") == "纯咨询闲聊":
        return {"ok": False, "message": "大模型判断该内容为纯咨询闲聊，未更新卡片"}
    _apply_extract_result(card_id, text, result)
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    return {"ok": True, "title": card["title"], "confidence": card["confidence"]}


def modify_card(card_id, user, instruction):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card or card["status"] != "pending":
        return
    if card["ai_round"] >= 3:
        bot.send_user_message(user, "本条需求已修改 3 轮仍未确认，请前往工作台网页端编辑后入池。", chat_id=card.get("chat_id"))
        return
    try:
        result = llm.modify(card, instruction or "请优化表述")
    except llm.LLMError:
        bot.send_user_message(user, "需求分析暂时失败，请稍后重试或前往网页端编辑。", chat_id=card.get("chat_id"))
        return
    db.execute(
        """UPDATE cards SET title=?, description=?, req_type=?, source_object=?, expect_time=?,
           urgency=?, confidence=?, ai_round=ai_round+1, updated_at=? WHERE id=?""",
        (
            (result.get("title") or card["title"] or "")[:30],
            (result.get("description") or card["description"] or "")[:500],
            result.get("intent") or card["req_type"],
            result.get("source_object") if result.get("source_object") is not None else card["source_object"],
            result.get("expect_time") if result.get("expect_time") is not None else card["expect_time"],
            result.get("urgency") or card["urgency"],
            float(result.get("confidence") or card["confidence"] or 0),
            db.now(),
            card_id,
        ),
    )
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    bot.send_card_message(card, user)


def _next_req_no():
    day = datetime.now().strftime("%Y%m%d")
    prefix = "XQ-%s-" % day
    row = db.query_one("SELECT MAX(req_no) AS m FROM requirements WHERE req_no LIKE ?", (prefix + "%",))
    seq = 0
    if row and row["m"]:
        try:
            seq = int(str(row["m"]).rsplit("-", 1)[-1])
        except ValueError:
            seq = 0
    return prefix + "%03d" % (seq + 1)


def _append_source(existing_json, source):
    try:
        items = json.loads(existing_json or "[]")
    except json.JSONDecodeError:
        items = []
    if source and source not in items:
        items.append(source)
    return json.dumps(items, ensure_ascii=False)


def confirm_card(card_id, operator, edits=None, decision=None):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card or card["status"] != "pending":
        return {"ok": False, "message": "卡片不存在或已处理"}
    if edits:
        manual = 0
        fields = {}
        for key in ("title", "description", "req_type", "module_id", "urgency", "source_object", "expect_time"):
            if key in edits and edits[key] is not None and str(edits[key]) != str(card.get(key) or ""):
                fields[key] = edits[key]
                manual = 1
        if fields:
            sets = ",".join(k + "=?" for k in fields)
            db.execute("UPDATE cards SET " + sets + ", manual_modified=?, updated_at=? WHERE id=?",
                       tuple(fields.values()) + (manual, db.now(), card_id))
            card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if decision == "merge":
        target_id = card["similar_requirement_id"]
        target = db.query_one("SELECT * FROM requirements WHERE id=?", (target_id,)) if target_id else None
        if not target:
            return {"ok": False, "message": "相似需求不存在，无法合并"}
        _merge_into(card, target, operator)
        return {"ok": True, "merged": True, "req_no": target["req_no"]}
    if decision != "new":
        threshold = float(db.get_config("similarity_threshold", "0.85"))
        similar = find_similar(card["title"] or "", card["description"] or "", threshold)
        if similar:
            db.execute("UPDATE cards SET pending_action='merge_prompt', similar_requirement_id=?, updated_at=? WHERE id=?",
                       (similar["requirement"]["id"], db.now(), card_id))
            req = similar["requirement"]
            return {"ok": False, "need_decision": True,
                    "similar": {"id": req["id"], "req_no": req["req_no"], "title": req["title"], "score": similar["score"]}}
    req = _create_requirement(card, operator)
    db.execute("UPDATE cards SET status='confirmed', pending_action='none', confirmed_at=?, updated_at=? WHERE id=?",
               (db.now(), db.now(), card_id))
    bot.send_user_message(
        card["source_user"],
        "您提交的需求已确认入池。需求编号：%s｜标题：%s" % (req["req_no"], req["title"]),
        chat_id=card.get("chat_id"),
    )
    return {"ok": True, "merged": False, "req_no": req["req_no"], "requirement_id": req["id"]}


def _create_requirement(card, operator):
    now = db.now()
    req_no = _next_req_no()
    module_id = None
    edits_module = card.get("module_id") if "module_id" in card.keys() else None
    if edits_module:
        module_id = edits_module
    req_id = db.execute(
        """INSERT INTO requirements(req_no,title,description,module_id,req_type,urgency,source_objects,
           expect_time,status,freq,created_by,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,'confirmed',1,?,?,?)""",
        (
            req_no,
            card["title"] or "未命名需求",
            card["description"] or "",
            module_id,
            card["req_type"] or "新需求",
            card["urgency"] or "中",
            _append_source("[]", card["source_object"]),
            card["expect_time"] or "",
            operator,
            now,
            now,
        ),
    )
    db.execute(
        "INSERT INTO evidences(requirement_id,card_id,source_user,raw_text,created_at) VALUES(?,?,?,?,?)",
        (req_id, card["id"], card["source_user"], card["masked_text"] or card["raw_text"], now),
    )
    db.execute(
        "INSERT INTO transitions(requirement_id,from_status,to_status,operator,reason,created_at) VALUES(?,?,?,?,?,?)",
        (req_id, None, "confirmed", operator, "确认入池", now),
    )
    db.execute("UPDATE attachments SET requirement_id=? WHERE card_id=?", (req_id, card["id"]))
    return db.query_one("SELECT * FROM requirements WHERE id=?", (req_id,))


def _merge_into(card, target, operator):
    now = db.now()
    db.execute(
        "UPDATE requirements SET freq=freq+1, source_objects=?, updated_at=? WHERE id=?",
        (_append_source(target["source_objects"], card["source_object"]), now, target["id"]),
    )
    db.execute(
        "INSERT INTO evidences(requirement_id,card_id,source_user,raw_text,created_at) VALUES(?,?,?,?,?)",
        (target["id"], card["id"], card["source_user"], card["masked_text"] or card["raw_text"], now),
    )
    db.execute(
        "INSERT INTO transitions(requirement_id,from_status,to_status,operator,reason,created_at) VALUES(?,?,?,?,?,?)",
        (target["id"], target["status"], target["status"], operator, "合并相似需求卡片 #%d" % card["id"], now),
    )
    db.execute("UPDATE cards SET status='confirmed', pending_action='none', confirmed_at=?, updated_at=? WHERE id=?",
               (now, now, card["id"]))
    db.execute("UPDATE attachments SET requirement_id=? WHERE card_id=?", (target["id"], card["id"]))
    bot.send_user_message(
        card["source_user"],
        "您提交的需求已合并至 %s（%s），提出次数+1。" % (target["req_no"], target["title"] or ""),
        chat_id=card.get("chat_id"),
    )


def ignore_card(card_id, operator):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card or card["status"] != "pending":
        return {"ok": False, "message": "卡片不存在或已处理"}
    db.execute("UPDATE cards SET status='ignored', pending_action='none', updated_at=? WHERE id=?", (db.now(), card_id))
    bot.send_user_message(card["source_user"], "您提交的需求未被采纳，如有疑问请联系产品负责人。", chat_id=card.get("chat_id"))
    return {"ok": True}


def restore_card(card_id):
    card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,))
    if not card or card["status"] != "ignored":
        return {"ok": False, "message": "卡片不存在或非已忽略状态"}
    db.execute("UPDATE cards SET status='pending', updated_at=? WHERE id=?", (db.now(), card_id))
    return {"ok": True}


def notify_released(req):
    rows = db.query("SELECT DISTINCT source_user FROM evidences WHERE requirement_id=?", (req["id"],))
    users = [r["source_user"] for r in rows if r["source_user"]]
    if not users and req.get("created_by"):
        users = [req["created_by"]]
    for name in users:
        bot.send_user_message(
            name,
            "您提出的需求已上线🎉 需求编号：%s｜标题：%s，感谢您的反馈！" % (req["req_no"], req["title"] or ""),
        )
    return len(users)


def notify_rejected(req):
    rows = db.query("SELECT DISTINCT source_user FROM evidences WHERE requirement_id=?", (req["id"],))
    users = [r["source_user"] for r in rows if r["source_user"]]
    if not users and req.get("created_by"):
        users = [req["created_by"]]
    for name in users:
        bot.send_user_message(
            name,
            "您提出的需求已拒绝 需求编号：%s｜标题：%s，拒绝原因：%s" % (req["req_no"], req["title"] or "", req["reject_reason"] or "未填写"),
        )
    return len(users)


def _notify_handlers(text):
    for row in db.query("SELECT name,wecom_userid FROM users WHERE role IN ('admin','leader')"):
        if bot.resolve_chatid(row["name"]) != row["name"]:
            bot.send_user_message(row["name"], text)


def sweep_reminders():
    rows = db.query("SELECT * FROM cards WHERE status='pending'")
    now_dt = datetime.now()
    for card in rows:
        created = _parse_time(card["created_at"])
        age = now_dt - created
        if age > timedelta(hours=48) and not card["reminded_48"]:
            _notify_handlers("提醒：需求卡片 #%d（%s）已等待确认超过 48 小时，请到「待确认收件箱」处理。" % (card["id"], card["title"] or ""))
            db.execute("UPDATE cards SET reminded_48=1, last_remind_at=? WHERE id=?", (db.now(), card["id"]))
        elif age > timedelta(days=7) and card["remind_count"] < 3:
            last = _parse_time(card["last_remind_at"]) if card["last_remind_at"] else created
            if now_dt - last >= timedelta(days=3):
                _notify_handlers("催办：需求卡片 #%d（%s）已超过 7 天未确认，请尽快到「待确认收件箱」处理。" % (card["id"], card["title"] or ""))
                db.execute("UPDATE cards SET remind_count=remind_count+1, last_remind_at=? WHERE id=?", (db.now(), card["id"]))
