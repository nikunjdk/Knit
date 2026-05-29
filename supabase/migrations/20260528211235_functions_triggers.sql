-- Auto-update updated_at on profiles and events
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Resolve canonical pair order for symmetric tables.
-- Always call this before inserting to connections, icebreaker_cache,
-- profile_similarity, or event_attendee_scores.
CREATE OR REPLACE FUNCTION canonical_pair(a UUID, b UUID)
RETURNS TABLE(user_a UUID, user_b UUID) AS $$
BEGIN
    IF a < b THEN
        RETURN QUERY SELECT a, b;
    ELSE
        RETURN QUERY SELECT b, a;
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
