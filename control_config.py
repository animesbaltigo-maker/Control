from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


_load_env_file()


@dataclass(frozen=True)
class BotTarget:
    id: str
    name: str
    base_url: str
    secret: str


def owner_id() -> int:
    return int(os.getenv("OWNER_ID", "1852596083"))


def owner_ids() -> set[int]:
    ids = {owner_id()}
    raw = os.getenv("OWNER_IDS", "").replace(";", ",")
    for chunk in raw.split(","):
        value = chunk.strip()
        if value.isdigit():
            ids.add(int(value))
    return ids


def bot_token() -> str:
    return os.getenv("BOT_TOKEN", "").strip()


def default_secret() -> str:
    return os.getenv("CONTROL_SECRET", "").strip()


def load_targets() -> list[BotTarget]:
    raw = (os.getenv("CONTROL_BOTS") or os.getenv("CONTROL_TARGETS") or "").strip()
    secret = default_secret()
    targets: list[BotTarget] = []
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split("|")]
        if len(parts) < 3:
            continue
        bot_id, name, base_url = parts[:3]
        item_secret = parts[3] if len(parts) >= 4 and parts[3] else secret
        if bot_id and name and base_url and item_secret:
            targets.append(BotTarget(bot_id, name, base_url.rstrip("/"), item_secret))
    return targets
