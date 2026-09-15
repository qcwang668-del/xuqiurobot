import secrets
import sqlite3
import threading
from datetime import datetime

from .config import DB_PATH, DEFAULT_CONFIGS
from .security import hash_password

_lock = threading.Lock()

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        wecom_userid TEXT,
        created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS modules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL DEFAULT '启用')""",
    """CREATE TABLE IF NOT EXISTS masking_words(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT UNIQUE NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS configs(
        key TEXT PRIMARY KEY,
        value TEXT)""",
    """CREATE TABLE IF NOT EXISTS buffers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        text TEXT NOT NULL,
        first_at TEXT,
        last_at TEXT,
        chat_id TEXT,
        processed INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS cards(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_user TEXT,
        raw_text TEXT,
        masked_text TEXT,
        title TEXT,
        description TEXT,
        req_type TEXT,
        source_object TEXT,
        expect_time TEXT,
        urgency TEXT DEFAULT '中',
        confidence REAL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        ai_round INTEGER NOT NULL DEFAULT 0,
        manual_modified INTEGER NOT NULL DEFAULT 0,
        pending_action TEXT NOT NULL DEFAULT 'none',
        module_id INTEGER,
        chat_id TEXT,
        similar_requirement_id INTEGER,
        reminded_48 INTEGER NOT NULL DEFAULT 0,
        remind_count INTEGER NOT NULL DEFAULT 0,
        last_remind_at TEXT,
        created_at TEXT,
        updated_at TEXT,
        confirmed_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS requirements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        req_no TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        module_id INTEGER,
        req_type TEXT,
        urgency TEXT DEFAULT '中',
        source_objects TEXT DEFAULT '[]',
        expect_time TEXT,
        status TEXT NOT NULL DEFAULT 'confirmed',
        reject_reason TEXT,
        freq INTEGER NOT NULL DEFAULT 1,
        created_by TEXT,
        created_at TEXT,
        updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS evidences(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requirement_id INTEGER NOT NULL,
        card_id INTEGER,
        source_user TEXT,
        raw_text TEXT,
        created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS transitions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requirement_id INTEGER NOT NULL,
        from_status TEXT,
        to_status TEXT,
        operator TEXT,
        reason TEXT,
        created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS broadcasts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        btype TEXT NOT NULL,
        biz_date TEXT,
        content TEXT,
        status TEXT,
        pushed_at TEXT,
        created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS ai_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER,
        request TEXT,
        response TEXT,
        latency_ms INTEGER,
        retries INTEGER DEFAULT 0,
        status TEXT,
        created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS bot_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        direction TEXT NOT NULL,
        user TEXT,
        msg_type TEXT DEFAULT 'text',
        content TEXT,
        created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS wecom_contacts(
        wecom_userid TEXT PRIMARY KEY,
        name TEXT NOT NULL DEFAULT '',
        first_seen TEXT,
        updated_at TEXT)""",
]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def query(sql, args=()):
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def query_one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    with _lock, connect() as conn:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid


def get_config(key, default=""):
    row = query_one("SELECT value FROM configs WHERE key=?", (key,))
    return row["value"] if row else default


def get_configs():
    return {r["key"]: r["value"] for r in query("SELECT key,value FROM configs")}


def set_config(key, value):
    execute(
        "INSERT INTO configs(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, "" if value is None else str(value)),
    )


def log_bot_message(direction, user, msg_type, content):
    return execute(
        "INSERT INTO bot_messages(direction,user,msg_type,content,created_at) VALUES(?,?,?,?,?)",
        (direction, user, msg_type, content, now()),
    )


def record_contact(userid):
    if not userid or userid == "unknown":
        return
    execute(
        "INSERT INTO wecom_contacts(wecom_userid,name,first_seen,updated_at) VALUES(?,'',?,?) ON CONFLICT(wecom_userid) DO NOTHING",
        (userid, now(), now()),
    )


def init_db():
    with connect() as conn:
        for stmt in SCHEMA:
            conn.execute(stmt)
        user_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "wecom_userid" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN wecom_userid TEXT")
        card_cols = [r[1] for r in conn.execute("PRAGMA table_info(cards)").fetchall()]
        if "chat_id" not in card_cols:
            conn.execute("ALTER TABLE cards ADD COLUMN chat_id TEXT")
        buf_cols = [r[1] for r in conn.execute("PRAGMA table_info(buffers)").fetchall()]
        if "chat_id" not in buf_cols:
            conn.execute("ALTER TABLE buffers ADD COLUMN chat_id TEXT")
        conn.commit()
    for key, value in DEFAULT_CONFIGS.items():
        if query_one("SELECT key FROM configs WHERE key=?", (key,)) is None:
            set_config(key, value)
    if query_one("SELECT key FROM configs WHERE key='auth_secret'") is None:
        set_config("auth_secret", secrets.token_hex(24))
    if query_one("SELECT id FROM users LIMIT 1") is None:
        t = now()
        execute("INSERT INTO users(username,password_hash,name,role,created_at) VALUES(?,?,?,?,?)",
                ("admin", hash_password("admin123"), "系统管理员", "admin", t))
        execute("INSERT INTO users(username,password_hash,name,role,created_at) VALUES(?,?,?,?,?)",
                ("leader", hash_password("leader123"), "产品负责人", "leader", t))
        execute("INSERT INTO users(username,password_hash,name,role,created_at) VALUES(?,?,?,?,?)",
                ("member", hash_password("member123"), "王雁", "member", t))
    if query_one("SELECT id FROM modules LIMIT 1") is None:
        for name in ("费控报销", "OA办公", "客户管理", "数据报表", "其他"):
            execute("INSERT INTO modules(name,status) VALUES(?,?)", (name, "启用"))
    member_names = {r["name"] for r in query("SELECT name FROM users")}
    known_userids = {r["wecom_userid"] for r in query("SELECT wecom_userid FROM users WHERE wecom_userid IS NOT NULL AND wecom_userid != ''")}
    for row in query("SELECT DISTINCT source_user AS su FROM cards UNION SELECT DISTINCT source_user AS su FROM evidences"):
        su = (row["su"] or "").strip()
        if su and su not in member_names and su not in known_userids:
            record_contact(su)
