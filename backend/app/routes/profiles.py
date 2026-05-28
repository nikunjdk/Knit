import hashlib
import json
import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_jwt
from app.core.redis import get_redis_client
from app.core.supabase import get_supabase_client
from app.models.profiles import EnrichProfileRequest, EnrichProfileResponse
from app.services.linkd import get_profile

logger = logging.getLogger(__name__)
router = APIRouter(tags=["profiles"])

_VALID_TAGS = {
    "AI/ML", "Web Dev", "Mobile", "DevOps", "Data", "Cybersecurity", "Open Source", "Blockchain",
    "Fintech", "Healthtech", "Edtech", "Climate", "SaaS", "Consumer", "B2B", "Deep Tech",
    "Founder", "Engineer", "Designer", "PM", "Marketer", "Researcher", "Investor", "Student",
    "Hiring", "Job Hunting", "Cofounder Search", "Investing", "Mentoring", "Collaborating", "Learning",
}

_HEADLINE_SPLITS = [" at ", " @ ", " | "]


def _extract_username(url: str) -> str | None:
    match = re.search(r"linkedin\.com/in/([^/?#]+)", url)
    return match.group(1).rstrip("/") if match else None


def _parse_headline(headline: str | None) -> tuple[str | None, str | None]:
    if not headline:
        return None, None
    for sep in _HEADLINE_SPLITS:
        if sep in headline:
            parts = headline.split(sep, 1)
            return parts[0].strip() or None, parts[1].strip() or None
    return headline.strip() or None, None


async def _map_interests_via_gemini(skills: list[str]) -> list[str]:
    from google import genai
    from app.core.config import get_settings

    client = genai.Client(api_key=get_settings().GEMINI_API_KEY)
    prompt = (
        f"Map these LinkedIn skills to the closest tags from this list: {sorted(_VALID_TAGS)}.\n"
        f"Return ONLY a JSON array of matching tags. Max 5. Only include tags from the provided list.\n"
        f"Skills: {skills}"
    )
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    text = response.text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("```").strip()
    try:
        tags = json.loads(text)
        return [t for t in tags if t in _VALID_TAGS][:5]
    except (json.JSONDecodeError, TypeError):
        logger.warning("Gemini tag mapping returned non-JSON: %s", text)
        return []


@router.post("/enrich-profile", response_model=EnrichProfileResponse)
async def enrich_profile(
    body: EnrichProfileRequest,
    user_id: str = Depends(verify_jwt),
):
    username = _extract_username(body.linkedin_url)
    if not username:
        raise HTTPException(status_code=422, detail="Could not extract LinkedIn username from URL")

    try:
        profile_data = await get_profile(username)
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail="LinkedIn enrichment service timed out")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=422, detail="LinkedIn profile not found")
        logger.exception("LinkdAPI error")
        raise HTTPException(status_code=503, detail="LinkedIn enrichment service unavailable")

    full_name = profile_data.get("full_name")
    avatar_url = profile_data.get("profile_pic_url")
    role, company = _parse_headline(profile_data.get("headline"))
    skills: list[str] = profile_data.get("skills") or []

    if not any([full_name, role, company, skills]):
        raise HTTPException(status_code=422, detail="No usable data returned from LinkedIn profile")

    # Tag mapping: Redis-cached per unique skill set (7 day TTL)
    interests: list[str] = []
    if skills:
        cache_key = f"tagmap:{hashlib.md5(json.dumps(sorted(skills)).encode()).hexdigest()}"
        redis = get_redis_client()
        cached = await redis.get(cache_key)
        if cached:
            try:
                raw = json.loads(cached)
                interests = [t for t in raw if t in _VALID_TAGS][:5]
            except (json.JSONDecodeError, TypeError):
                interests = []
        else:
            try:
                mapped = await _map_interests_via_gemini(skills)
                interests = [t for t in mapped if t in _VALID_TAGS][:5]
                await redis.set(cache_key, json.dumps(interests), ex=7 * 24 * 3600)
            except Exception:
                logger.warning("Tag mapping failed — continuing without interests")
                interests = []

    # Persist enriched fields (service role — no RLS)
    update_payload: dict = {}
    if full_name:
        update_payload["full_name"] = full_name
    if avatar_url:
        update_payload["avatar_url"] = avatar_url
    if role:
        update_payload["role"] = role
    if company:
        update_payload["company"] = company
    if body.linkedin_url:
        update_payload["linkedin_url"] = body.linkedin_url
    if interests:
        update_payload["interests"] = interests

    if update_payload:
        try:
            sb = await get_supabase_client()
            await sb.table("profiles").update(update_payload).eq("id", user_id).execute()
        except Exception:
            logger.exception("Failed to update profile after enrichment")
            # Non-fatal — return the enriched data even if persist fails

    return EnrichProfileResponse(
        full_name=full_name,
        role=role,
        company=company,
        interests=interests,
        linkedin_url=body.linkedin_url,
        avatar_url=avatar_url,
    )
