import asyncio
from typing import AsyncGenerator

from google import genai

from app.core.config import get_settings


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


async def generate_stream(prompt: str) -> AsyncGenerator[str, None]:
    client = _get_client()
    async for chunk in await client.aio.models.generate_content_stream(
        model="gemini-2.0-flash",
        contents=prompt,
    ):
        if chunk.text:
            yield chunk.text
