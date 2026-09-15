import json
import time

import httpx

from . import db

EXTRACT_PROMPT = """你是需求分析助手，负责把产品经理在企业微信中提交的消息提炼为结构化需求卡片。
消息内容：
%s
请仅输出 JSON（不要输出 Markdown 代码块及其他内容），结构如下：
{
  "intent": "新需求|体验优化|缺陷反馈|纯咨询闲聊",
  "title": "需求标题，不超过30字，概括核心诉求",
  "description": "需求描述，包含业务场景与期望效果，不超过500字",
  "source_object": "来源对象（客户/部门/个人），无法识别为空字符串",
  "expect_time": "原文中的期望时间表述，无法识别为空字符串",
  "urgency": "高|中|低",
  "confidence": 0到1之间的数值，表示提炼置信度
}
判定规则：消息仅为咨询、寒暄、通知且无明确诉求时，intent 输出"纯咨询闲聊"；存在明确功能或体验改进诉求时按类型输出；紧急度依据原文语气与期望时间紧迫性判断，默认"中"。"""

MODIFY_PROMPT = """你是需求分析助手。以下是已提炼的需求卡片 JSON 与提出人的修改意见，请结合修改意见更新卡片内容。
原卡片：
%s
修改意见：
%s
请仅输出更新后的 JSON（结构与原卡片一致，不要输出其他内容）：
{
  "intent": "新需求|体验优化|缺陷反馈",
  "title": "不超过30字",
  "description": "不超过500字",
  "source_object": "无法识别为空字符串",
  "expect_time": "无法识别为空字符串",
  "urgency": "高|中|低",
  "confidence": 0到1之间的数值
}"""


class LLMError(Exception):
    pass


def _chat(messages, timeout, retries=3):
    cfg = db.get_configs()
    api_key = cfg.get("model_api_key", "")
    if not api_key:
        raise LLMError("missing_api_key")
    url = cfg.get("model_base_url", "").rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.get("model_name", "ark-code-latest"),
        "messages": messages,
        "temperature": 0.2,
    }
    last_err = None
    for attempt in range(retries):
        try:
            resp = httpx.post(
                url,
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            last_err = exc
    raise LLMError(str(last_err))


def _parse_json(content):
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("invalid_json")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("invalid_json: %s" % exc)


def _log(card_id, request, response, latency_ms, retries, status):
    db.execute(
        "INSERT INTO ai_logs(card_id,request,response,latency_ms,retries,status,created_at) VALUES(?,?,?,?,?,?,?)",
        (card_id, request[:4000], (response or "")[:4000], latency_ms, retries, status, db.now()),
    )


def _mock_extract(text):
    low = text.lower()
    if len(text.strip()) < 4 or low in ("在吗", "你好", "hi", "hello", "谢谢", "收到"):
        return {"intent": "纯咨询闲聊", "title": "", "description": "", "source_object": "", "expect_time": "", "urgency": "中", "confidence": 0.9}
    intent = "新需求"
    if any(k in text for k in ("报错", "错误", "失败", "bug", "BUG", "异常", "打不开", "不能用")):
        intent = "缺陷反馈"
    elif any(k in text for k in ("优化", "改进", "建议", "希望", "能不能", "可不可以")):
        intent = "体验优化"
    urgency = "高" if any(k in text for k in ("紧急", "尽快", "马上", "月底", "本周", "今天")) else "中"
    title = text.strip().replace("\n", " ")[:28]
    return {"intent": intent, "title": title, "description": text.strip()[:480], "source_object": "", "expect_time": "", "urgency": urgency, "confidence": 0.5}


def extract(text, card_id=None):
    cfg = db.get_configs()
    if not cfg.get("model_api_key"):
        result = _mock_extract(text)
        _log(card_id, "MOCK_EXTRACT\n" + text, json.dumps(result, ensure_ascii=False), 0, 0, "mock")
        return result
    prompt = EXTRACT_PROMPT % text
    timeout = float(cfg.get("model_timeout", "30"))
    started = time.time()
    retries = 0
    try:
        content = _chat([{"role": "user", "content": prompt}], timeout, retries=3)
    except LLMError as exc:
        _log(card_id, prompt, str(exc), int((time.time() - started) * 1000), 2, "failed")
        raise
    try:
        result = _parse_json(content)
    except LLMError:
        retries = 1
        try:
            content = _chat([{"role": "user", "content": prompt}], timeout, retries=1)
            result = _parse_json(content)
        except LLMError as exc:
            _log(card_id, prompt, str(exc), int((time.time() - started) * 1000), retries, "failed")
            raise
    _log(card_id, prompt, json.dumps(result, ensure_ascii=False), int((time.time() - started) * 1000), retries, "success")
    return result


SIMILAR_PROMPT = """你是需求去重助手。以下是新需求与需求池中的候选需求列表，请判断新需求是否与某个候选表达同一诉求（语义相似，表述不同也算）。
新需求标题：%s
新需求描述：%s
候选列表：
%s
请仅输出 JSON（不要输出其他内容）：
{"index": 命中的候选序号（从0开始），无命中输出 -1, "score": 0到1之间的相似度，无命中输出0}"""


def judge_similar(title, description, candidates):
    if not db.get_config("model_api_key"):
        return None
    cand_text = "\n".join(
        "%d. [%s] %s ｜ %s" % (i, c["req_no"], c["title"], (c["description"] or "")[:100])
        for i, c in enumerate(candidates)
    )
    prompt = SIMILAR_PROMPT % (title, description[:300], cand_text)
    timeout = float(db.get_config("model_timeout", "30"))
    started = time.time()
    try:
        content = _chat([{"role": "user", "content": prompt}], timeout, retries=2)
        result = _parse_json(content)
        index = int(result.get("index", -1))
        score = float(result.get("score", 0))
    except (LLMError, ValueError, TypeError) as exc:
        _log(None, prompt, str(exc), int((time.time() - started) * 1000), 1, "failed")
        return None
    _log(None, prompt, content[:4000], int((time.time() - started) * 1000), 0, "success")
    if index < 0:
        return None
    return {"index": index, "score": score}


def modify(card, instruction):
    cfg = db.get_configs()
    card_json = json.dumps({
        "intent": card.get("req_type") or "",
        "title": card.get("title") or "",
        "description": card.get("description") or "",
        "source_object": card.get("source_object") or "",
        "expect_time": card.get("expect_time") or "",
        "urgency": card.get("urgency") or "中",
        "confidence": card.get("confidence") or 0,
    }, ensure_ascii=False)
    if not cfg.get("model_api_key"):
        result = json.loads(card_json)
        if instruction:
            for level in ("高", "中", "低"):
                if ("紧急度" in instruction or "紧急" in instruction) and level in instruction:
                    result["urgency"] = level
            for marker in ("标题改成", "标题改为", "标题：", "标题:"):
                if marker in instruction:
                    result["title"] = instruction.split(marker, 1)[1].strip()[:28]
                    break
            result["description"] = (result["description"] + "；补充：" + instruction)[:480]
            result["confidence"] = 0.5
        _log(card.get("id"), "MOCK_MODIFY\n" + instruction, json.dumps(result, ensure_ascii=False), 0, 0, "mock")
        return result
    prompt = MODIFY_PROMPT % (card_json, instruction)
    timeout = float(cfg.get("model_timeout", "30"))
    started = time.time()
    try:
        content = _chat([{"role": "user", "content": prompt}], timeout, retries=2)
        result = _parse_json(content)
    except LLMError as exc:
        _log(card.get("id"), prompt, str(exc), int((time.time() - started) * 1000), 1, "failed")
        raise
    _log(card.get("id"), prompt, json.dumps(result, ensure_ascii=False), int((time.time() - started) * 1000), 0, "success")
    return result
