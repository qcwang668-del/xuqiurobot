import asyncio
import json
import re
import time
from pathlib import Path

from . import db
from .config import DATA_DIR

HELP_TEXT = (
    "【需求助手使用说明】\n"
    "1. 直接把需求以文字发给我，我会自动整理后请你确认；\n"
    "2. 整理完成后请在「需求搜集智能工作台 → 待确认收件箱」中确认，处理结果会私信通知您；\n"
    "3. 需求上线后也会第一时间通知您；\n"
    "4. 本期暂支持文字提报。"
)

_adapter = None
_connected = False


def register_adapter(adapter):
    global _adapter
    _adapter = adapter


def get_adapter():
    return _adapter


def set_connected(value):
    global _connected
    _connected = value


def is_connected():
    return _connected


def resolve_user_name(userid):
    row = db.query_one("SELECT name FROM users WHERE wecom_userid=?", (userid,))
    if row:
        return row["name"]
    db.record_contact(userid)
    contact = db.query_one("SELECT name FROM wecom_contacts WHERE wecom_userid=?", (userid,))
    if contact and contact["name"]:
        return contact["name"]
    return userid


def maybe_resolve_sender(user):
    """在线程池中调用：未识别的企微 UserID 尝试通过通讯录接口解析姓名。"""
    if not user or not user.startswith("wo"):
        return user
    if db.query_one("SELECT id FROM users WHERE name=?", (user,)):
        return user
    from . import wecom_api
    name = wecom_api.fetch_user_names([user]).get(user)
    if name:
        db.execute("UPDATE wecom_contacts SET name=?, updated_at=? WHERE wecom_userid=?", (name, db.now(), user))
        return name
    return user


def resolve_chatid(user):
    row = db.query_one("SELECT wecom_userid FROM users WHERE name=?", (user,))
    if row and row["wecom_userid"]:
        return row["wecom_userid"]
    contact = db.query_one("SELECT wecom_userid FROM wecom_contacts WHERE name=? ORDER BY updated_at DESC", (user,))
    if contact:
        return contact["wecom_userid"]
    return user


def send_user_message(user, content, msg_type="markdown", chat_id=None):
    db.log_bot_message("out", user, msg_type, content)
    if db.get_config("bot_mode", "mock") != "wecom" or not _adapter:
        return
    _adapter.send(chat_id or resolve_chatid(user), {"msgtype": "markdown", "markdown": {"content": content}})


def send_group_message(group, content):
    db.log_bot_message("out", "group:" + group, "markdown", content)


def format_card_message(card):
    lines = [
        "【需求确认卡片 #%d】" % card["id"],
        "标题：" + (card["title"] or ""),
        "类型：" + (card["req_type"] or "") + " ｜ 紧急度：" + (card["urgency"] or "中") + " ｜ 置信度：%.2f" % (card["confidence"] or 0),
    ]
    if card.get("source_object"):
        lines.append("来源：" + card["source_object"])
    if card.get("expect_time"):
        lines.append("期望时间：" + card["expect_time"])
    if (card.get("confidence") or 0) < 0.6:
        lines.append("提炼质量较低，请重点核对")
    lines.append("描述：" + (card["description"] or ""))
    return "\n".join(lines)


def build_confirm_template_card(card):
    sub_lines = [
        "类型：" + (card["req_type"] or "") + " ｜ 紧急度：" + (card["urgency"] or "中") + " ｜ 置信度：%.2f" % (card["confidence"] or 0),
    ]
    if card.get("source_object"):
        sub_lines.append("来源：" + card["source_object"])
    if card.get("expect_time"):
        sub_lines.append("期望时间：" + card["expect_time"])
    if (card.get("confidence") or 0) < 0.6:
        sub_lines.append("提炼质量较低，请重点核对")
    sub_lines.append("描述：" + (card["description"] or "")[:140])
    return {
        "card_type": "button_interaction",
        "source": {"desc": "需求搜集智能工作台"},
        "main_title": {"title": "需求确认卡片 #%d" % card["id"], "desc": (card["title"] or "")[:60]},
        "sub_title_text": "\n".join(sub_lines),
        "task_id": "reqcard_%d_%d" % (card["id"], int(time.time() * 1000)),
        "button_list": [
            {"text": "确认入池", "style": 1, "key": "confirm:%d" % card["id"]},
            {"text": "修改", "style": 2, "key": "modify:%d" % card["id"]},
            {"text": "忽略", "style": 3, "key": "ignore:%d" % card["id"]},
        ],
    }


def send_card_message(card, user=None):
    target = user or card["source_user"]
    if db.get_config("bot_mode", "mock") == "wecom" and _adapter:
        db.log_bot_message("out", target, "template_card", format_card_message(card))
        _adapter.send(
            card.get("chat_id") or resolve_chatid(target),
            {"msgtype": "template_card", "template_card": build_confirm_template_card(card)},
        )
    else:
        db.log_bot_message("out", target, "markdown", format_card_message(card))


def _log_frame(frame):
    try:
        with open(Path(DATA_DIR) / "wecom_frames.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(frame, ensure_ascii=False)[:2000] + "\n")
    except Exception:
        pass


def _log_conn(event, detail=""):
    try:
        with open(Path(DATA_DIR) / "wecom_conn.log", "a", encoding="utf-8") as f:
            f.write("%s %s %s\n" % (db.now(), event, detail))
    except Exception:
        pass


def _strip_mention(text):
    return re.sub(r"^(@\S+\s*)+", "", (text or "").strip())


class WeComBotAdapter:
    """企业微信智能机器人官方 SDK 长连接适配器（wecom-aibot-sdk）。"""

    def __init__(self, bot_id, secret, loop):
        from wecom_aibot_sdk import WSClient

        self._loop = loop
        self.client = WSClient(bot_id, secret)
        self._register_events()

    def _register_events(self):
        self.client.on("authenticated", lambda: (set_connected(True), _log_conn("authenticated")))
        self.client.on("disconnected", lambda reason: (set_connected(False), _log_conn("disconnected", reason)))
        self.client.on("message.text", self._on_text)
        for event in ("message.image", "message.voice", "message.file", "message.video", "message.mixed"):
            self.client.on(event, self._on_non_text)
        self.client.on("event.enter_chat", self._on_enter_chat)
        self.client.on("event.template_card_event", self._on_card_event)

    @staticmethod
    def _sender_id(frame):
        body = frame.get("body") or {}
        return (body.get("from") or {}).get("userid") or body.get("chatid") or "unknown"

    @staticmethod
    def _chat_id(frame):
        body = frame.get("body") or {}
        return body.get("chatid") or None

    def _run_pipeline(self, func, *args):
        self._loop.run_in_executor(None, func, *args)

    def _on_text(self, frame):
        from . import pipeline

        _log_frame(frame)
        body = frame.get("body") or {}
        content = _strip_mention((body.get("text") or {}).get("content", ""))
        if not content:
            return
        user = resolve_user_name(self._sender_id(frame))
        self._run_pipeline(pipeline.handle_incoming, user, content, "wecom", self._chat_id(frame))

    def _on_non_text(self, frame):
        from . import pipeline

        body = frame.get("body") or {}
        user = resolve_user_name(self._sender_id(frame))
        self._run_pipeline(pipeline.handle_non_text, user, body.get("msgtype", "unknown"))

    def _on_enter_chat(self, frame):
        async def _welcome():
            try:
                await self.client.reply_welcome(frame, {"msgtype": "text", "text": {"content": HELP_TEXT}})
            except Exception:
                pass

        asyncio.run_coroutine_threadsafe(_welcome(), self._loop)

    def _on_card_event(self, frame):
        from . import pipeline

        _log_frame(frame)
        body = frame.get("body") or {}
        event = body.get("event") or {}
        detail = event.get("template_card_event") or {}
        key = detail.get("event_key") or event.get("button_key") or event.get("event_key") or ""
        task_id = detail.get("task_id") or ""
        user = resolve_user_name(self._sender_id(frame))
        chat_id = self._chat_id(frame)
        if ":" not in key:
            return
        action, _, sid = key.partition(":")
        try:
            card_id = int(sid)
        except ValueError:
            return
        if action == "confirm":
            self._run_card_action(frame, pipeline.confirm_card, card_id, user, task_id, "确认入池")
        elif action == "ignore":
            self._run_card_action(frame, pipeline.ignore_card, card_id, user, task_id, "忽略")
        elif action == "modify":
            send_user_message(user, "请前往「需求搜集智能工作台 → 待确认收件箱」使用「编辑后入池」处理。", chat_id=chat_id)

    def _run_card_action(self, frame, func, card_id, user, task_id, label):
        future = self._loop.run_in_executor(None, func, card_id, user)

        def _done(fut):
            try:
                result = fut.result() or {}
            except Exception as exc:
                print("[bot] 卡片操作执行失败:", exc)
                result = {}
            if result.get("ok"):
                text = "处理结果：%s（操作人：%s）" % (label, user)
            elif result.get("need_decision"):
                text = "已提交：检测到相似需求，请在「待确认收件箱」选择合并或新建"
            else:
                text = "处理失败：%s" % (result.get("message") or "卡片可能已被处理")
            card = db.query_one("SELECT * FROM cards WHERE id=?", (card_id,)) or {"id": card_id}
            done_card = {
                "card_type": "button_interaction",
                "source": {"desc": "需求搜集智能工作台"},
                "main_title": {"title": "需求确认卡片 #%d" % card_id, "desc": (card.get("title") or "")[:60]},
                "sub_title_text": "标题：%s\n%s" % (card.get("title") or "", text),
                "task_id": task_id or ("reqcard_%d" % card_id),
                "button_list": [{"text": "已处理", "style": 2, "key": "done:%d" % card_id}],
            }
            asyncio.run_coroutine_threadsafe(self.client.update_template_card(frame, done_card), self._loop)

        future.add_done_callback(_done)

    async def start(self):
        await self.client.connect()

    def send(self, chatid, body):
        future = asyncio.run_coroutine_threadsafe(self.client.send_message(chatid, body), self._loop)

        def _log_error(fut):
            exc = fut.exception()
            if exc:
                print("[bot] 消息发送失败:", chatid, exc)
                try:
                    with open(Path(DATA_DIR) / "bot_send_errors.log", "a", encoding="utf-8") as f:
                        f.write("%s chatid=%s error=%s\n" % (db.now(), chatid, exc))
                except Exception:
                    pass

        future.add_done_callback(_log_error)
