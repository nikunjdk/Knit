import asyncio
from typing import AsyncGenerator

import google.generativeai as genai

from app.core.config import get_settings


def _configure() -> None:
    genai.configure(api_key=get_settings().GEMINI_API_KEY)


async def embed_text(text: str) -> list[float]:
    _configure()
    result = await asyncio.to_thread(
        genai.embed_content,
        model="models/text-embedding-004",
        content=text,
    )
    return result["embedding"]


async def generate_stream(prompt: str) -> AsyncGenerator[str, None]:
    _configure()
    model = genai.GenerativeModel("gemini-2.0-flash")
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _producer() -> None:
        try:
            for chunk in model.generate_content(prompt, stream=True):
                if chunk.text:
                    loop.call_soon_threadsafe(queue.put_nowait, chunk.text)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, _producer)
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item
