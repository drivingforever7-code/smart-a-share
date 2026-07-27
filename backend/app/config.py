from __future__ import annotations

import os

from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent


def _load_local_env() -> None:
    """读取项目根目录 .env；不覆盖系统已经设置的环境变量。"""
    path = PROJECT_DIR / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_local_env()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    project_dir: Path = PROJECT_DIR
    app_name: str = "智选 A 股数据服务"
    version: str = "0.1.0"
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            f"sqlite:///{(DATA_DIR / 'smart_a_share.db').as_posix()}",
        )
    )
    quote_cache_seconds: int = 8
    quote_stale_seconds: int = 300
    default_history_days: int = 420
    new_stock_days: int = 120
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""),
        repr=False,
    )
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    deepseek_model: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    )


settings = Settings()
