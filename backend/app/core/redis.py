from functools import lru_cache
import httpx
from app.core.config import get_settings


class RedisClient:
    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _cmd(self, *args: object) -> object:
        async with httpx.AsyncClient() as client:
            r = await client.post(self._url, json=list(args), headers=self._headers)
            r.raise_for_status()
            return r.json().get("result")

    async def get(self, key: str) -> str | None:
        return await self._cmd("GET", key)  # type: ignore[return-value]

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if ex:
            await self._cmd("SET", key, value, "EX", ex)
        else:
            await self._cmd("SET", key, value)

    async def incr(self, key: str) -> int:
        return await self._cmd("INCR", key)  # type: ignore[return-value]

    async def expire(self, key: str, seconds: int) -> None:
        await self._cmd("EXPIRE", key, seconds)

    async def exists(self, key: str) -> bool:
        result = await self._cmd("EXISTS", key)
        return result == 1

    async def delete(self, key: str) -> None:
        await self._cmd("DEL", key)


@lru_cache
def get_redis_client() -> RedisClient:
    s = get_settings()
    return RedisClient(s.UPSTASH_REDIS_URL, s.UPSTASH_REDIS_TOKEN)
