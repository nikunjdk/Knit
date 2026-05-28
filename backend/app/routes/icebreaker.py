import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import verify_jwt
from app.core.redis import get_redis_client
from app.core.supabase import get_supabase_client
from app.services.gemini import generate_stream, increment_gemini_counter
from app.services.scoring import canonical_pair

logger = logging.getLogger(__name__)
router = APIRouter(tags=["icebreaker"])

_CIRCUIT_BREAKER_KEY = "circuit_breaker:open"
_ICEBREAKER_TTL = 7 * 24 * 3600


def _cache_key(event_id: str, uid_a: str, uid_b: str) -> str:
    return f"icebreaker:{event_id}:{uid_a}:{uid_b}"


def _build_prompt(profile_a: dict, profile_b: dict, agenda_a: str, agenda_b: str) -> str:
    def _desc(p: dict, agenda: str) -> str:
        parts = []
        if p.get("role"):
            parts.append(p["role"])
        if p.get("company"):
            parts.append(f"at {p['company']}")
        interests = p.get("interests") or []
        if interests:
            parts.append(f"interests: {', '.join(interests)}")
        if agenda:
            parts.append(f"event goal: {agenda}")
        return ", ".join(parts) if parts else "professional"

    return (
        "You are helping two professionals connect at a networking event. "
        "Create 3 concise, personalized icebreaker questions.\n\n"
        f"Person A: {_desc(profile_a, agenda_a)}\n"
        f"Person B: {_desc(profile_b, agenda_b)}\n\n"
        "Generate 3 specific questions Person A could ask Person B that reference their "
        "backgrounds. Be warm, curious, and professional. Return only the numbered questions."
    )


def _sse_stream(content: str) -> StreamingResponse:
    async def _gen():
        yield f"data: {json.dumps({'chunk': content})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        _gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/icebreaker/stream")
async def stream_icebreaker(
    event_id: str = Query(...),
    other_user_id: str = Query(...),
    user_id: str = Depends(verify_jwt),
):
    redis = get_redis_client()
    uid_a, uid_b = canonical_pair(user_id, other_user_id)
    key = _cache_key(event_id, uid_a, uid_b)

    # 1. Redis cache hit
    cached = await redis.get(key)
    if cached:
        return _sse_stream(cached)

    sb = await get_supabase_client()

    # 2. Postgres cache hit
    try:
        pg = (
            await sb.table("icebreaker_cache")
            .select("content")
            .eq("event_id", event_id)
            .eq("user_a_id", uid_a)
            .eq("user_b_id", uid_b)
            .maybe_single()
            .execute()
        )
        if pg.data:
            content = pg.data["content"]
            await redis.set(key, content, ex=_ICEBREAKER_TTL)
            return _sse_stream(content)
    except Exception:
        logger.exception("Postgres icebreaker cache lookup failed")

    # 3. Circuit breaker check
    if await redis.get(_CIRCUIT_BREAKER_KEY):
        raise HTTPException(status_code=429, detail="AI service temporarily unavailable")

    # 4. Fetch both attendee profiles + agendas
    try:
        result = (
            await sb.table("event_attendees")
            .select("user_id, agenda, profiles(role, company, interests)")
            .eq("event_id", event_id)
            .in_("user_id", [user_id, other_user_id])
            .execute()
        )
        rows = {r["user_id"]: r for r in (result.data or [])}
    except Exception:
        logger.exception("Failed to fetch attendees for icebreaker")
        raise HTTPException(status_code=500, detail="Failed to fetch event data")

    if user_id not in rows or other_user_id not in rows:
        raise HTTPException(status_code=404, detail="One or both users not found in this event")

    row_a, row_b = rows[user_id], rows[other_user_id]
    prompt = _build_prompt(
        profile_a=row_a.get("profiles") or {},
        profile_b=row_b.get("profiles") or {},
        agenda_a=row_a.get("agenda") or "",
        agenda_b=row_b.get("agenda") or "",
    )

    # 5. Stream + 6. Cache on complete
    async def _generate_and_cache():
        collected: list[str] = []
        try:
            async for chunk in generate_stream(prompt):
                collected.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            full_content = "".join(collected)

            try:
                await sb.table("icebreaker_cache").upsert({
                    "event_id": event_id,
                    "user_a_id": uid_a,
                    "user_b_id": uid_b,
                    "content": full_content,
                }).execute()
            except Exception:
                logger.exception("Failed to persist icebreaker to Postgres")

            try:
                await redis.set(key, full_content, ex=_ICEBREAKER_TTL)
            except Exception:
                logger.exception("Failed to persist icebreaker to Redis")

            try:
                await increment_gemini_counter(redis)
            except Exception:
                logger.exception("Failed to increment Gemini counter")

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception:
            logger.exception("Gemini stream failed")
            yield f"data: {json.dumps({'error': 'STREAM_ERROR'})}\n\n"

    return StreamingResponse(
        _generate_and_cache(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
