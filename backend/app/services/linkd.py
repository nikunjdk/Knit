import httpx

from app.core.config import get_settings

_BASE = "https://api.linkd.dev/v1"
_TIMEOUT = 3.0


async def get_profile(username: str) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            f"{_BASE}/profile/full",
            params={"username": username},
            headers={"Authorization": f"Bearer {get_settings().LINKD_API_KEY}"},
        )
        r.raise_for_status()
        return r.json()
