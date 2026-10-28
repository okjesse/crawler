"""路径与全局配置。"""
from __future__ import annotations

import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PKG_DIR / "templates"
PRODUCT_MAP_PATH = PKG_DIR / "product_map.yaml"

# 数据目录：原始 HTML 缓存、SQLite、导出文件。可用环境变量覆盖。
DATA_DIR = Path(os.environ.get("FC_DATA_DIR", Path.cwd() / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "faculty.sqlite"
EXPORT_DIR = DATA_DIR / "export"

# 抓取礼貌参数
MIN_INTERVAL_SEC = float(os.environ.get("FC_MIN_INTERVAL", "2.5"))
TIMEOUT_SEC = float(os.environ.get("FC_TIMEOUT", "30"))
MAX_RETRIES = int(os.environ.get("FC_MAX_RETRIES", "3"))
RESPECT_ROBOTS = os.environ.get("FC_RESPECT_ROBOTS", "1") != "0"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
]


def ensure_dirs() -> None:
    for d in (DATA_DIR, RAW_DIR, EXPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)
