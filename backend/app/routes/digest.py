import json
import logging
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import verify_jwt
from app.core.redis import get_redis_client
from app.core.supabase import get_supabase_client
from app.services.gemini import generate_stream, increment_gemini_counter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["digest"])

_CIRCUIT_BREAKER_KEY = "circuit_breaker:open"
_DIGEST_CAP = 3


def _compute_stats(attendees: list[dict], connections: list[dict]) -> dict:
    n = len(attendees)
    c = len(connections)
    max_pairs = n * (n - 1) / 2
    density = round(c / max_pairs, 4) if max_pairs > 0 else 0.0

    tag_counter: Counter = Counter()
    for att in attendees:
        profile = att.get("profiles") or {}
        for tag in profile.get("interests") or []:
            tag_counter[tag] += 1
    top_tags = [tag for tag, _ in tag_counter.most_common(3)]

    return {
        "attendee_count": n,
        "connection_count": c,
        "top_tags": top_tags,
        "connection_density": density,
    }


def _build_digest_prompt(event: dict, stats: dict) -> str:
    tag_str = ", ".join(stats["top_tags"]) if stats["top_tags"] else "diverse topics"
    return (
        f"You are writing a post-event digest for organizers.\n\n"
        f"Event: {event.get('title', 'Networking Event')}\n"
        f"Attendees: {stats['attendee_count']}\n"
        f"Connections made: {stats['connection_count']}\n"
        f"Top interests: {tag_str}\n"
        f"Connection density: {stats['connection_density']:.1%}\n\n"
        "Write a warm, insightful 3-paragraph digest for the organizer covering: "
        "1) who attended and the energy of the event, "
        "2) notable connections and themes that emerged, "
        "3) suggestions for the next event. "
        "Be specific, positive, and actionable. Keep it under 250 words."
    )


@router.get("/digest/stream")
async def stream_digest(
    event_id: str = Query(...),
    user_id: str = Depends(verify_jwt),
):
    redis = get_redis_client()
    sb = await get_supabase_client()

    # Fetch event — check organizer and cap
    try:
        event_result = (
            await sb.table("events")
            .select("id, organizer_id, digest_generation_count, title")
            .eq("id", event_id)
            .single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to fetch event for digest")
        raise HTTPException(status_code=500, detail="Failed to fetch event")

    event = event_result.data
    if event["organizer_id"] != user_id:
        raise HTTPException(status_code=403, detail="Only the event organizer can generate a digest")

    if event["digest_generation_count"] >= _DIGEST_CAP:
        raise HTTPException(status_code=403, detail="DIGEST_CAP_REACHED")

    # Circuit breaker check
    if await redis.get(_CIRCUIT_BREAKER_KEY):
        raise HTTPException(status_code=429, detail="AI service temporarily unavailable")

    # Fetch attendees with profile interests for stats
    try:
        att_result = (
            await sb.table("event_attendees").select("user_id, profiles(interests)").eq("event_id", event_id).execute()
        )
        attendees = att_result.data or []
    except Exception:
        logger.exception("Failed to fetch attendees for digest")
        attendees = []

    # Fetch connections for density stat
    try:
        conn_result = await sb.table("connections").select("id").eq("event_id", event_id).execute()
        connections = conn_result.data or []
    except Exception:
        logger.exception("Failed to fetch connections for digest")
        connections = []

    stats = _compute_stats(attendees, connections)
    prompt = _build_digest_prompt(event, stats)

    async def _generate():
        # Stats always sent first so the UI can populate the bar before text arrives
        yield f"data: {json.dumps({'stats': stats})}\n\n"

        collected: list[str] = []
        try:
            async for chunk in generate_stream(prompt):
                collected.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception:
            logger.exception("Gemini digest stream failed")
            yield f"data: {json.dumps({'error': 'STREAM_ERROR'})}\n\n"
            return

        # Atomic increment — Postgres is authoritative; Redis is fast-path only
        try:
            inc_result = await sb.rpc(
                "increment_digest_count",
                {"p_event_id": event_id, "p_cap": _DIGEST_CAP},
            ).execute()
            new_count = (inc_result.data or [{}])[0].get("digest_generation_count", _DIGEST_CAP)
        except Exception:
            logger.exception("Failed to increment digest count")
            new_count = _DIGEST_CAP

        try:
            await increment_gemini_counter(redis)
        except Exception:
            logger.exception("Failed to increment Gemini counter")

        yield f"data: {json.dumps({'done': True, 'generations_remaining': _DIGEST_CAP - new_count})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
