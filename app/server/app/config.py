import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "app.db"

DEFAULT_CONFIGS = {
    "model_base_url": os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3"),
    "model_name": os.environ.get("ARK_MODEL", "ark-code-latest"),
    "model_api_key": os.environ.get("ARK_API_KEY", ""),
    "model_timeout": "30",
    "similarity_threshold": "0.85",
    "merge_window_seconds": "300",
    "buffer_idle_seconds": "10",
    "bot_mode": os.environ.get("BOT_MODE", "mock"),
    "bot_id": os.environ.get("WECOM_BOT_ID", ""),
    "bot_secret": os.environ.get("WECOM_BOT_SECRET", ""),
    "wecom_corpid": os.environ.get("WECOM_CORPID", ""),
    "wecom_contact_secret": os.environ.get("WECOM_CONTACT_SECRET", ""),
    "broadcast_daily_time": "18:00",
    "broadcast_weekly_day": "5",
    "broadcast_weekly_time": "18:00",
    "broadcast_webhooks": "",
}
