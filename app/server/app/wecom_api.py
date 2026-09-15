import json
import time
import urllib.request

from . import db

BASE = "https://qyapi.weixin.qq.com"

_token_cache = {"token": "", "expires": 0.0}


def _call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def get_token():
    corpid = db.get_config("wecom_corpid")
    secret = db.get_config("wecom_contact_secret")
    if not corpid or not secret:
        return ""
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]
    res = _call("GET", BASE + "/cgi-bin/gettoken?corpid=%s&corpsecret=%s" % (corpid, secret))
    token = res.get("access_token", "")
    if token:
        _token_cache["token"] = token
        _token_cache["expires"] = time.time() + int(res.get("expires_in", 7200)) - 300
    else:
        print("[wecom] gettoken 失败:", res.get("errcode"), res.get("errmsg"))
    return token


def fetch_user_names(open_userids):
    """通过自建应用接口把 open_userid 列表解析为 {open_userid: name}，失败返回空 dict。"""
    ids = [u for u in dict.fromkeys(open_userids) if u]
    if not ids:
        return {}
    try:
        token = get_token()
    except Exception as exc:
        print("[wecom] gettoken 异常:", exc)
        return {}
    if not token:
        return {}
    try:
        conv = _call("POST", BASE + "/cgi-bin/batch/openuserid_to_userid?access_token=" + token,
                     {"open_userid_list": ids})
    except Exception as exc:
        print("[wecom] open_userid 转换异常:", exc)
        return {}
    if conv.get("errcode") != 0:
        print("[wecom] open_userid 转换失败:", conv.get("errcode"), conv.get("errmsg"))
        return {}
    names = {}
    for item in conv.get("userid_list", []):
        try:
            info = _call("GET", BASE + "/cgi-bin/user/get?access_token=%s&userid=%s" % (token, item["userid"]))
        except Exception as exc:
            print("[wecom] 读取成员异常:", item.get("userid"), exc)
            continue
        if info.get("name"):
            names[item["open_userid"]] = info["name"]
        else:
            print("[wecom] 读取成员失败:", item.get("userid"), info.get("errcode"), info.get("errmsg"))
    return names


def sync_contacts():
    """解析名单里所有未命名的 UserID，返回 (成功数, 总数)。"""
    rows = db.query("SELECT wecom_userid FROM wecom_contacts WHERE name = ''")
    names = fetch_user_names([r["wecom_userid"] for r in rows])
    for open_userid, name in names.items():
        db.execute("UPDATE wecom_contacts SET name=?, updated_at=? WHERE wecom_userid=?", (name, db.now(), open_userid))
    return len(names), len(rows)
