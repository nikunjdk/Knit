import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_jwt
from app.core.redis import get_redis_client
from app.core.supabase import get_supabase_client
from app.models.profiles import EmbeddingRecomputeRequest
from app.services.gemini import embed_text
from app.services.scoring import canonical_pair, cosine_similarity

logger = logging.getLogger(__name__)
router = APIRouter(tags=["embeddings"])

_CIRCUIT_BREAKER_KEY = "circuit_breaker:open"
_DAILY_COUNT_KEY = "gemini:daily_count"


def _build_profile_text(profile: dict) -> str:
    parts: list[str] = []
    if profile.get("role"):
        parts.append(profile["role"])
    if profile.get("company"):
        parts.append(f"at {profile['company']}")
    interests: list[str] = profile.get("interests") or []
    if interests:
        parts.append(f"Interests: {', '.join(interests)}")
    return " ".join(parts) if parts else "professional"


@router.post("/embeddings/recompute", status_code=202)
async def recompute_embeddings(
    body: EmbeddingRecomputeRequest,
    user_id: str = Depends(verify_jwt),
):
    redis = get_redis_client()

    # Circuit breaker check — must happen before any Gemini call
    if await redis.get(_CIRCUIT_BREAKER_KEY):
        raise HTTPException(status_code=429, detail="AI service temporarily unavailable")

    sb = await get_supabase_client()

    # Fetch profile
    try:
        profile_result = (
            await sb.table("profiles")
            .select("id, role, company, interests")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception:
        logger.exception("Failed to fetch profile for embedding")
        raise HTTPException(status_code=500, detail="Failed to fetch profile")

    profile = profile_result.data
    profile_text = _build_profile_text(profile)

    # Embed profile
    try:
        profile_vector = await embed_text(profile_text)
        await _increment_gemini_counter(redis)
    except Exception:
        logger.exception("Gemini embed failed for profile")
        raise HTTPException(status_code=503, detail="Embedding service unavailable")

    # Persist profile embedding
    try:
        await sb.table("profiles").update({"profile_embedding": profile_vector}).eq("id", user_id).execute()
    except Exception:
        logger.exception("Failed to persist profile embedding")

    # If no event_id, we're done
    if not body.event_id:
        return {"status": "ok"}

    # Fetch current user's event agenda
    try:
        attendee_result = (
            await sb.table("event_attendees")
            .select("agenda")
            .eq("event_id", body.event_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        agenda = (attendee_result.data or {}).get("agenda") or ""
    except Exception:
        agenda = ""

    # Build event-scoped text and embed
    event_text = profile_text
    if agenda:
        event_text = f"{profile_text} Event goal: {agenda}"

    try:
        event_vector = await embed_text(event_text)
        await _increment_gemini_counter(redis)
    except Exception:
        logger.exception("Gemini embed failed for event embedding")
        raise HTTPException(status_code=503, detail="Embedding service unavailable")

    # Persist event embedding
    try:
        await sb.table("event_attendees").update(
            {"event_embedding": event_vector}
        ).eq("event_id", body.event_id).eq("user_id", user_id).execute()
    except Exception:
        logger.exception("Failed to persist event embedding")

    # Fetch other attendees' event embeddings and compute scores
    try:
        others_result = (
            await sb.table("event_attendees")
            .select("user_id, event_embedding")
            .eq("event_id", body.event_id)
            .neq("user_id", user_id)
            .execute()
        )
        others = [r for r in (others_result.data or []) if r.get("event_embedding")]
    except Exception:
        logger.exception("Failed to fetch other attendees for scoring")
        return {"status": "ok"}

    for other in others:
        other_id = other["user_id"]
        score = cosine_similarity(event_vector, other["event_embedding"])
        uid_a, uid_b = canonical_pair(user_id, other_id)
        try:
            await sb.table("event_attendee_scores").upsert({
                "event_id": body.event_id,
                "user_a_id": uid_a,
                "user_b_id": uid_b,
                "score": score,
            }).execute()
        except Exception:
            logger.exception("Failed to upsert score for pair (%s, %s)", uid_a, uid_b)

    return {"status": "ok"}


async def _increment_gemini_counter(redis) -> None:
    count = await redis.incr(_DAILY_COUNT_KEY)
    if count == 1:
        # First call today — set TTL to midnight UTC
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        ttl = int((midnight - now).total_seconds())
        await redis.expire(_DAILY_COUNT_KEY, ttl)
    if count >= 1200:
        await redis.set("circuit_breaker:open", "1", ex=86400)
