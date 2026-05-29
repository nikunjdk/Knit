-- Atomic digest count increment with cap enforcement.
-- Returns the updated row so the caller knows the new count.
-- If count is already at p_cap, no update is made and no row is returned
-- (caller should treat 0 rows as cap-already-reached).
CREATE OR REPLACE FUNCTION increment_digest_count(p_event_id UUID, p_cap INT)
RETURNS TABLE(digest_generation_count INT) AS $$
BEGIN
    RETURN QUERY
    UPDATE events
    SET digest_generation_count = events.digest_generation_count + 1
    WHERE id = p_event_id
      AND events.digest_generation_count < p_cap
    RETURNING events.digest_generation_count;
END;
$$ LANGUAGE plpgsql;
