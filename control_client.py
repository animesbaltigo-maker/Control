from __future__ import annotations

from typing import Any

import httpx

from control_config import BotTarget


class ControlClient:
    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def _request(self, target: BotTarget, method: str, path: str, **kwargs) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        headers["X-Control-Secret"] = target.secret
        url = f"{target.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
            data = response.json()
            if not isinstance(data, dict):
                data = {"ok": False, "error": "invalid_response"}
            data.setdefault("http_status", response.status_code)
            data.setdefault("bot_id", target.id)
            data.setdefault("name", target.name)
            return data
        except Exception as exc:
            return {"ok": False, "bot_id": target.id, "name": target.name, "error": str(exc), "offline": True}

    async def health(self, target: BotTarget) -> dict[str, Any]:
        return await self._request(target, "GET", "/control/health")

    async def metrics(self, target: BotTarget, period: str = "total") -> dict[str, Any]:
        return await self._request(target, "GET", "/control/metrics", params={"period": period})

    async def block(self, target: BotTarget, user_id: int, *, username: str = "", actor_id: int = 0) -> dict[str, Any]:
        return await self._request(
            target,
            "POST",
            "/control/block",
            json={"user_id": int(user_id), "username": username, "actor_id": int(actor_id)},
        )

    async def broadcast(self, target: BotTarget, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(target, "POST", "/control/broadcast", json=payload, timeout=self.timeout)
