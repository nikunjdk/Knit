import asyncio
import datetime
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from google import genai

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.core.redis import RedisClient

logger = logging.getLogger(__name__)

_CIRCUIT_BREAKER_KEY = "circuit_breaker:open"
_DAILY_COUNT_KEY = "gemini:daily_count"
_DAILY_LIMIT = 1200


def _get_client() -> genai.Client:
    return genai.Client(api_key=get_settings().GEMINI_API_KEY)


async def embed_text(text: str) -> list[float]:
    client = _get_client()
    result = await asyncio.to_thread(
        client.models.embed_content,
        model="text-embedding-004",
        contents=text,
    )
    return result.embeddings[0].values


async def generate_stream(prompt: str) -> AsyncGenerator[str]:
    client = _get_client()
    async for chunk in await client.aio.models.generate_content_stream(
        model="gemini-2.0-flash",
        contents=prompt,
    ):
        if chunk.text:
            yield chunk.text


async def increment_gemini_counter(redis: "RedisClient") -> None:
    count = await redis.incr(_DAILY_COUNT_KEY)
    if count == 1:
        now = datetime.datetime.now(datetime.UTC)
        midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        await redis.expire(_DAILY_COUNT_KEY, int((midnight - now).total_seconds()))
    if count >= _DAILY_LIMIT:
        await redis.set(_CIRCUIT_BREAKER_KEY, "1", ex=86400)
        logger.warning("Gemini daily limit reached — circuit breaker opened")
